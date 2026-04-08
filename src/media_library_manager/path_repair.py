from __future__ import annotations

from difflib import SequenceMatcher
from datetime import UTC, datetime
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .folder_index import filter_index_candidates_for_provider
from .models import RootConfig
from .providers.base import ProviderError
from .providers.radarr import RadarrClient
from .rclone_cli import list_entries_recursive
from .providers.sonarr import SonarrClient
from .storage import StoragePath, default_storage_manager
from .sync_integrations import build_provider_config, normalize_title


YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")
TITLE_STOPWORDS = {"the", "a", "an", "of", "and", "for", "to", "in"}
RELEASE_NOISE_TOKENS = {
    "2160p",
    "1080p",
    "720p",
    "480p",
    "4k",
    "uhd",
    "hdr",
    "dv",
    "dovi",
    "bluray",
    "brrip",
    "bdrip",
    "webrip",
    "webdl",
    "web",
    "remux",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "av1",
    "aac",
    "dts",
    "atmos",
    "proper",
    "repack",
    "extended",
    "internal",
    "readnfo",
}
LIBRARY_JUNK_TOKENS = {
    "season",
    "seasons",
    "special",
    "specials",
    "extras",
    "extra",
    "featurette",
    "featurettes",
    "sample",
    "samples",
    "trickplay",
    "subtitle",
    "subtitles",
    "subs",
}
EPISODE_TOKEN_RE = re.compile(r"\bs\d{1,2}e\d{1,3}\b", re.IGNORECASE)


def scan_provider_path_issues(
    integrations: dict[str, Any],
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    start_provider_index: int = 1,
) -> dict[str, Any]:
    _ = roots
    _ = lan_connections
    providers = [provider for provider in ["radarr", "sonarr"] if integrations.get(provider, {}).get("enabled")]
    issues: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_providers = len(providers)

    normalized_start_index = max(1, int(start_provider_index or 1))
    for index, provider in enumerate(providers[normalized_start_index - 1 :], start=normalized_start_index):
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "provider_started",
                    "provider": provider,
                    "index": index,
                    "total_providers": total_providers,
                }
            )
        config = build_provider_config(integrations.get(provider, {}))
        try:
            items = _list_provider_items(provider, config)
        except ProviderError as exc:
            errors.append({"provider": provider, "message": str(exc)})
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "provider_failed",
                        "provider": provider,
                        "index": index,
                        "total_providers": total_providers,
                        "message": str(exc),
                        "total_errors": len(errors),
                    }
                )
            continue

        if progress_callback is not None:
            progress_callback(
                {
                    "event": "provider_items_loaded",
                    "provider": provider,
                    "index": index,
                    "total_providers": total_providers,
                    "items": len(items),
                }
            )
        issues_before = len(issues)
        total_items = len(items)
        for item_index, item in enumerate(items, start=1):
            if not _should_include_item_in_path_repair_scan(provider, item):
                if progress_callback is not None and (item_index == total_items or item_index == 1 or item_index % 25 == 0):
                    progress_callback(
                        {
                            "event": "provider_item_progress",
                            "provider": provider,
                            "index": index,
                            "total_providers": total_providers,
                            "item_index": item_index,
                            "total_items": total_items,
                            "total_issues": len(issues),
                        }
                    )
                continue
            issues.append(_build_issue(provider, item, reason="item_missing"))

            if progress_callback is not None and (item_index == total_items or item_index == 1 or item_index % 25 == 0):
                progress_callback(
                    {
                        "event": "provider_item_progress",
                        "provider": provider,
                        "index": index,
                        "total_providers": total_providers,
                        "item_index": item_index,
                        "total_items": total_items,
                        "total_issues": len(issues),
                    }
                )
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "provider_completed",
                    "provider": provider,
                    "index": index,
                    "total_providers": total_providers,
                    "items": len(items),
                    "issues_found": len(issues) - issues_before,
                    "total_issues": len(issues),
                    "total_errors": len(errors),
                }
            )

    if progress_callback is not None:
        progress_callback(
            {
                "event": "scan_completed",
                "total_providers": total_providers,
                "issues": len(issues),
                "errors": len(errors),
            }
        )

    return {
        "version": 1,
        "summary": {
            "providers": total_providers,
            "issues": len(issues),
            "errors": len(errors),
        },
        "issues": issues,
        "errors": errors,
    }


def _is_item_missing_in_provider(provider: str, item: dict[str, Any]) -> bool:
    if provider == "radarr":
        if "hasFile" not in item:
            return False
        return not bool(item.get("hasFile"))
    if provider == "sonarr":
        stats = item.get("statistics") or {}
        episode_count = int(stats.get("episodeCount") or 0)
        episode_file_count = int(stats.get("episodeFileCount") or 0)
        return episode_count > 0 and episode_file_count == 0
    return False


def _should_include_item_in_path_repair_scan(provider: str, item: dict[str, Any]) -> bool:
    if provider == "radarr":
        return _is_item_released_in_provider(provider, item) and _is_item_missing_in_provider(provider, item)
    if provider == "sonarr":
        return _is_item_missing_in_provider(provider, item)
    return False


def _is_item_released_in_provider(provider: str, item: dict[str, Any]) -> bool:
    if provider != "radarr":
        return True
    if "isAvailable" in item:
        return bool(item.get("isAvailable"))
    for key in ("physicalRelease", "digitalRelease", "inCinemas"):
        if _provider_date_has_reached(item.get(key)):
            return True
    return False


def _provider_date_has_reached(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = text.replace("Z", "+00:00")
    try:
        release_at = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if release_at.tzinfo is None:
        release_at = release_at.replace(tzinfo=UTC)
    return release_at <= datetime.now(UTC)


def update_provider_item_path(integrations: dict[str, Any], *, provider: str, item_id: int, new_path: str) -> dict[str, Any]:
    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}

    resolved_path = str(Path(new_path).expanduser().resolve())
    try:
        if provider == "radarr":
            client = RadarrClient(config)
            movie = client.get_movie(int(item_id))
            movie["path"] = resolved_path
            updated = client.update_movie(movie)
            refresh = client.refresh_movie(int(item_id))
        elif provider == "sonarr":
            client = SonarrClient(config)
            series = client.get_series(int(item_id))
            series["path"] = resolved_path
            updated = client.update_series(series)
            refresh = client.refresh_series(int(item_id))
        else:
            return {"status": "error", "message": f"unsupported provider: {provider}"}
    except ProviderError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "success",
        "provider": provider,
        "item_id": item_id,
        "path": updated.get("path", resolved_path),
        "refresh": refresh,
    }


def delete_provider_item(
    integrations: dict[str, Any],
    *,
    provider: str,
    item_id: int,
    add_import_exclusion: bool = False,
) -> dict[str, Any]:
    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}

    try:
        if provider == "radarr":
            client = RadarrClient(config)
            # For Radarr, manually handle exclusion if requested
            movie_details = None
            if add_import_exclusion:
                try:
                    movie_details = client.get_movie(item_id)
                except Exception:
                    pass

            result = client.delete_movie(item_id, delete_files=False, add_import_exclusion=add_import_exclusion)

            if add_import_exclusion and movie_details and movie_details.get("tmdbId"):
                try:
                    client.post(
                        "/api/v3/importlistexclusion",
                        {
                            "tmdbId": movie_details["tmdbId"],
                            "title": movie_details.get("title") or "Unknown Movie",
                            "year": movie_details.get("year") or 0,
                        },
                    )
                except Exception:
                    pass
        elif provider == "sonarr":
            client = SonarrClient(config)
            # For Sonarr, manually handle exclusion if requested because the DELETE parameter is unreliable
            series_details = None
            if add_import_exclusion:
                try:
                    series_details = client.get_series(item_id)
                except Exception:
                    pass

            result = client.delete_series(item_id, delete_files=False, add_import_exclusion=add_import_exclusion)

            if add_import_exclusion and series_details and series_details.get("tvdbId"):
                try:
                    client.post(
                        "/api/v3/importlistexclusion",
                        {
                            "tvdbId": series_details["tvdbId"],
                            "title": series_details.get("title") or "Unknown Series",
                        },
                    )
                except Exception:
                    # Ignore errors adding to exclusion list after successful delete
                    pass
        else:
            return {"status": "error", "message": f"unsupported provider: {provider}"}
    except ProviderError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "success",
        "provider": provider,
        "item_id": item_id,
        "delete_files": False,
        "add_import_exclusion": add_import_exclusion,
        "result": result,
    }


def find_path_repair_suggestions(
    *,
    provider: str,
    item: dict[str, Any],
    roots: list[RootConfig],
    manager: Any,
    max_depth: int = 8,
    max_suggestions: int = 6,
) -> list[dict[str, Any]]:
    aliases = _build_search_aliases(item)
    year = int(item.get("year") or 0) or None
    candidates = _index_provider_candidates(provider=provider, roots=roots, manager=manager, max_depth=max_depth)
    return _rank_candidates(candidates, aliases=aliases, year=year, max_suggestions=max_suggestions)


def search_library_paths(
    *,
    provider: str,
    query: str,
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    folder_index_report: dict[str, Any] | None = None,
    max_depth: int = 8,
    max_results: int = 20,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    normalized_query = normalize_title(query)
    if not normalized_query:
        return []
    aliases = [normalized_query]

    cached_results = _search_cached_index_matches(
        provider=provider,
        query=query,
        roots=roots,
        folder_index_report=folder_index_report,
        aliases=aliases,
        max_results=max_results,
    )
    if cached_results:
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "cache_hit",
                    "provider": provider,
                    "query": query,
                    "generated_at": folder_index_report.get("generated_at") if isinstance(folder_index_report, dict) else None,
                    "candidate_count": len(filter_index_candidates_for_provider(provider=provider, roots=roots, report=folder_index_report)),
                    "result_count": len(cached_results),
                }
            )
        return cached_results

    manager = default_storage_manager(lan_connections=lan_connections)
    provider_roots = _iter_provider_roots(provider, roots)
    if progress_callback is not None and folder_index_report:
        progress_callback(
            {
                "event": "cache_miss",
                "provider": provider,
                "query": query,
            }
        )
    if progress_callback is not None:
        progress_callback(
            {
                "event": "search_started",
                "provider": provider,
                "query": query,
                "normalized_query": normalized_query,
                "root_count": len(provider_roots),
                "max_depth": max_depth,
            }
        )
    results: list[dict[str, Any]] = []
    primary_kind = _primary_root_kind(provider)
    total_roots = len(provider_roots)
    total_indexed_folders = 0
    for root_index, root in enumerate(provider_roots, start=1):
        root_storage_path = _root_to_storage_path(root)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "root_index_started",
                    "provider": provider,
                    "provider_index": 1,
                    "total_providers": 1,
                    "root_index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                }
            )
        root_results, indexed_folders, exact_match_found = _search_root_matches(
            manager,
            root,
            root_storage_path,
            aliases=aliases,
            year=None,
            max_depth=max_depth,
            max_results=max_results,
        )
        total_indexed_folders += indexed_folders
        results = _merge_ranked_results(results, root_results, max_results=max_results)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "root_index_completed",
                    "provider": provider,
                    "provider_index": 1,
                    "total_providers": 1,
                    "root_index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "indexed_folders": indexed_folders,
                    "total_indexed_folders": total_indexed_folders,
                }
            )
        if results and root.kind == primary_kind and exact_match_found:
            break

    if progress_callback is not None:
        progress_callback(
            {
                "event": "search_completed",
                "provider": provider,
                "query": query,
                "candidate_count": total_indexed_folders,
                "result_count": len(results),
            }
        )
    return results


def _search_cached_index_matches(
    *,
    provider: str,
    query: str,
    roots: list[RootConfig],
    folder_index_report: dict[str, Any] | None,
    aliases: list[str],
    max_results: int,
) -> list[dict[str, Any]]:
    cached_candidates = filter_index_candidates_for_provider(provider=provider, roots=roots, report=folder_index_report)
    if not cached_candidates:
        return []
    ranked = _rank_candidates(cached_candidates, aliases=aliases, year=None, max_suggestions=max_results)
    if ranked:
        return ranked
    normalized_query = normalize_title(query)
    if not normalized_query:
        return []
    return _rank_candidates(cached_candidates, aliases=[normalized_query], year=None, max_suggestions=max_results, min_score=80)


def _index_provider_candidates(
    *,
    provider: str,
    roots: list[RootConfig],
    manager: Any,
    max_depth: int = 8,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    provider_index: int | None = None,
    total_providers: int | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    provider_roots = _iter_provider_roots(provider, roots)
    total_roots = len(provider_roots)

    for root_index, root in enumerate(provider_roots, start=1):
        root_storage_path = _root_to_storage_path(root)
        indexed_before = len(candidates)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "root_index_started",
                    "provider": provider,
                    "provider_index": provider_index,
                    "total_providers": total_providers,
                    "root_index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                }
            )
        candidates.extend(_collect_root_matches(manager, root, root_storage_path, max_depth=max_depth))
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "root_index_completed",
                    "provider": provider,
                    "provider_index": provider_index,
                    "total_providers": total_providers,
                    "root_index": root_index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "indexed_folders": len(candidates) - indexed_before,
                    "total_indexed_folders": len(candidates),
                }
            )
    return candidates


def _collect_root_matches(manager: Any, root: RootConfig, current: StoragePath, *, max_depth: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    root_storage_path = _root_to_storage_path(root)
    pending: list[tuple[StoragePath, int]] = [(current, 0)]
    while pending:
        path, depth = pending.pop()
        if depth > max_depth:
            continue
        try:
            entries = manager.list_dir(path)
        except Exception:
            continue
        for entry in entries:
            if not entry.is_dir:
                continue
            candidate_name = entry.name
            matches.append(
                {
                    "label": candidate_name,
                    "normalized_name": normalize_title(candidate_name),
                    "path": _storage_entry_display_path(root=root, root_storage_path=root_storage_path, entry_path=entry.path),
                    "storage_uri": entry.path.to_uri(),
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "kind": root.kind,
                    "depth": depth + 1,
                }
            )
            pending.append((entry.path, depth + 1))
    return matches


def _search_root_matches(
    manager: Any,
    root: RootConfig,
    current: StoragePath,
    *,
    aliases: list[str],
    year: int | None,
    max_depth: int,
    max_results: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    if current.backend == "rclone":
        return _search_rclone_root_matches(
            root,
            current,
            aliases=aliases,
            year=year,
            max_results=max_results,
        )

    matches: list[dict[str, Any]] = []
    root_storage_path = _root_to_storage_path(root)
    pending: list[tuple[StoragePath, int]] = [(current, 0)]
    indexed_folders = 0
    exact_match_found = False

    while pending:
        path, depth = pending.pop()
        if depth > max_depth:
            continue
        try:
            entries = manager.list_dir(path)
        except Exception:
            continue
        for entry in entries:
            if not entry.is_dir:
                continue
            indexed_folders += 1
            candidate = {
                "label": entry.name,
                "normalized_name": normalize_title(entry.name),
                "path": _storage_entry_display_path(root=root, root_storage_path=root_storage_path, entry_path=entry.path),
                "storage_uri": entry.path.to_uri(),
                "root_label": root.label,
                "root_path": str(root.path),
                "kind": root.kind,
                "depth": depth + 1,
            }
            matches = _merge_ranked_results(
                matches,
                _rank_candidates([candidate], aliases=aliases, year=year, max_suggestions=max_results),
                max_results=max_results,
            )
            if any(int(item.get("score", 0)) >= 120 for item in matches):
                exact_match_found = True
            if exact_match_found:
                return matches, indexed_folders, True
            pending.append((entry.path, depth + 1))

    return matches, indexed_folders, exact_match_found


def _search_rclone_root_matches(
    root: RootConfig,
    root_storage_path: StoragePath,
    *,
    aliases: list[str],
    year: int | None,
    max_results: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    filtered_rows = list_entries_recursive(
        root_storage_path.rclone_remote,
        root_storage_path.normalized_path(),
        dirs_only=True,
        fast_list=True,
        include_patterns=_build_rclone_include_patterns(aliases),
    )
    rows = filtered_rows or list_entries_recursive(
        root_storage_path.rclone_remote,
        root_storage_path.normalized_path(),
        dirs_only=True,
        fast_list=True,
    )
    matches: list[dict[str, Any]] = []
    exact_match_found = False
    indexed_folders = 0
    for row in rows:
        if not bool(row.get("IsDir", True)):
            continue
        raw_relative_path = str(row.get("Path") or row.get("Name") or "").strip().strip("/")
        if not raw_relative_path:
            continue
        indexed_folders += 1
        relative_parts = [segment for segment in raw_relative_path.split("/") if segment and segment != "."]
        if not relative_parts:
            continue
        entry_path = root_storage_path.join(*relative_parts)
        candidate = {
            "label": relative_parts[-1],
            "normalized_name": normalize_title(relative_parts[-1]),
            "path": _storage_entry_display_path(root=root, root_storage_path=root_storage_path, entry_path=entry_path),
            "storage_uri": entry_path.to_uri(),
            "root_label": root.label,
            "root_path": str(root.path),
            "kind": root.kind,
            "depth": len(relative_parts),
        }
        matches = _merge_ranked_results(
            matches,
            _rank_candidates([candidate], aliases=aliases, year=year, max_suggestions=max_results),
            max_results=max_results,
        )
        if any(int(item.get("score", 0)) >= 120 for item in matches):
            exact_match_found = True
            break
    return matches, indexed_folders, exact_match_found


def _build_rclone_include_patterns(aliases: list[str]) -> list[str]:
    patterns: list[str] = []
    for alias in aliases:
        text = str(alias or "").strip()
        if not text:
            continue
        variants = {
            text,
            text.lower(),
            text.upper(),
            text.title(),
            text.replace(" ", "*"),
            text.lower().replace(" ", "*"),
        }
        for variant in variants:
            clean_variant = str(variant or "").strip()
            if clean_variant:
                patterns.append(f"*{clean_variant}*")
    deduped: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        if pattern in seen:
            continue
        seen.add(pattern)
        deduped.append(pattern)
    return deduped


def _merge_ranked_results(existing: list[dict[str, Any]], new_items: list[dict[str, Any]], *, max_results: int) -> list[dict[str, Any]]:
    if not existing:
        return list(new_items[:max_results])
    merged: dict[str, dict[str, Any]] = {str(item.get("path") or ""): item for item in existing}
    for item in new_items:
        path = str(item.get("path") or "")
        if not path:
            continue
        current = merged.get(path)
        if current is None or int(item.get("score", 0)) > int(current.get("score", 0)):
            merged[path] = item
    ranked = sorted(merged.values(), key=lambda item: (-int(item.get("score", 0)), str(item.get("path") or "").lower()))
    return ranked[:max_results]


def _storage_entry_display_path(*, root: RootConfig, root_storage_path: StoragePath, entry_path: StoragePath) -> str:
    if entry_path.backend == "local":
        return entry_path.normalized_path()
    relative = entry_path.relative_to(root_storage_path)
    parts = [segment for segment in str(relative).split("/") if segment and segment != "."]
    if not parts:
        return str(root.path)
    return str(Path(root.path).joinpath(*parts))


def _rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    aliases: list[str],
    year: int | None,
    max_suggestions: int = 6,
    min_score: int = 70,
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        score = _score_candidate(candidate, aliases=aliases, year=year)
        if score >= min_score:
            ranked.append((score, candidate))

    ranked.sort(key=lambda item: (-item[0], item[1]["path"].lower()))
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, candidate in ranked:
        path = candidate["path"]
        if path in seen:
            continue
        seen.add(path)
        suggestions.append({k: v for k, v in candidate.items() if k != "normalized_name"} | {"score": score})
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def _score_candidate(candidate: dict[str, Any] | str, *, aliases: list[str], year: int | None) -> int:
    if isinstance(candidate, dict):
        name = str(candidate.get("normalized_name", "") or candidate.get("label", ""))
        root_kind = str(candidate.get("kind") or "mixed")
        depth = int(candidate.get("depth", 0) or 0)
        label = str(candidate.get("label") or "")
        path = str(candidate.get("path") or "")
    else:
        name = str(candidate or "")
        root_kind = "mixed"
        depth = 0
        label = str(candidate or "")
        path = ""
    normalized_name = name if " " in str(name) else normalize_title(name)
    aliases = [alias for alias in aliases if alias]
    if not normalized_name or not aliases:
        return 0
    score = max(_score_alias(normalized_name, alias) for alias in aliases)
    if year:
        matched_year = YEAR_RE.search(normalized_name)
        if matched_year and matched_year.group(1) == str(year):
            score += 15
        elif matched_year:
            score -= 20
    if root_kind != "mixed":
        score += 5
    score -= _candidate_penalty(label=label, path=path, depth=depth, aliases=aliases)
    return max(score, 0)


def _candidate_penalty(*, label: str, path: str, depth: int, aliases: list[str]) -> int:
    penalty = 0
    normalized_label = normalize_title(label)
    label_tokens = set(_meaningful_title_tokens(normalized_label))
    raw_text = f"{label} {path}".lower()

    if EPISODE_TOKEN_RE.search(raw_text):
        penalty += 50

    if label_tokens & LIBRARY_JUNK_TOKENS:
        penalty += 35

    extra_depth = max(depth - 2, 0)
    penalty += extra_depth * 8

    alias_token_lengths = [len(_meaningful_title_tokens(alias)) for alias in aliases if alias]
    if alias_token_lengths:
        shortest_alias = min(alias_token_lengths)
        label_token_count = len(_meaningful_title_tokens(normalized_label))
        if shortest_alias <= 1 and label_token_count >= 3:
            penalty += 30
        elif shortest_alias > 0 and label_token_count >= shortest_alias + 3:
            penalty += 12

    return penalty


def _build_issue(provider: str, item: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "id": f"{provider}:{item.get('id')}",
        "provider": provider,
        "item_id": item.get("id"),
        "title": item.get("title"),
        "year": item.get("year"),
        "path": item.get("path"),
        "reason": reason,
    }


def _list_provider_items(provider: str, config: Any) -> list[dict[str, Any]]:
    if provider == "radarr":
        return RadarrClient(config).list_movies()
    if provider == "sonarr":
        return SonarrClient(config).list_series()
    raise ProviderError(f"unsupported provider: {provider}")


def _root_to_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://", "rclone://")):
        return StoragePath.from_uri(raw)
    return StoragePath.local(raw)


def _iter_provider_roots(provider: str, roots: list[RootConfig]) -> list[RootConfig]:
    matched: list[RootConfig] = []
    for root in roots:
        if provider == "radarr" and root.kind not in {"movie", "mixed"}:
            continue
        if provider == "sonarr" and root.kind not in {"series", "mixed"}:
            continue
        matched.append(root)
    primary_kind = _primary_root_kind(provider)
    return sorted(matched, key=lambda root: (0 if root.kind == primary_kind else 1, str(root.label or "").lower(), str(root.path)))


def _primary_root_kind(provider: str) -> str:
    return "movie" if provider == "radarr" else "series"


def _build_search_aliases(item: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    title = normalize_title(item.get("title", ""))
    if title:
        aliases.append(title)

    raw_path = str(item.get("path") or "").strip()
    if raw_path:
        path = Path(raw_path)
        for candidate in [path.name, path.parent.name]:
            normalized = normalize_title(candidate)
            if normalized and normalized not in aliases:
                aliases.append(normalized)
    return aliases


def _score_alias(normalized_name: str, alias: str) -> int:
    candidate_tokens = _meaningful_title_tokens(normalized_name)
    alias_tokens = _meaningful_title_tokens(alias)
    if not candidate_tokens or not alias_tokens:
        return 0

    if candidate_tokens == alias_tokens:
        return 120

    alias_token_set = set(alias_tokens)
    candidate_token_set = set(candidate_tokens)
    if not alias_token_set.issubset(candidate_token_set):
        return 0

    match_positions: list[int] = []
    search_start = 0
    for token in alias_tokens:
        try:
            position = candidate_tokens.index(token, search_start)
        except ValueError:
            position = candidate_tokens.index(token)
        match_positions.append(position)
        search_start = position + 1

    ordered = match_positions == sorted(match_positions)
    contiguous = ordered and match_positions[-1] - match_positions[0] + 1 == len(match_positions)
    alias_text = " ".join(alias_tokens)
    candidate_text = " ".join(candidate_tokens)
    ratio = SequenceMatcher(None, candidate_text, alias_text).ratio()

    if contiguous and candidate_tokens[: len(alias_tokens)] == alias_tokens:
        return 112 + int(ratio * 8)
    if contiguous:
        return 102 + int(ratio * 8)
    if ordered:
        return 92 + int(ratio * 10)
    return 82 + int(ratio * 10)


def _meaningful_title_tokens(value: str) -> list[str]:
    tokens = TITLE_TOKEN_RE.findall(str(value).lower())
    filtered = [
        token
        for token in tokens
        if token not in TITLE_STOPWORDS and token not in RELEASE_NOISE_TOKENS and not YEAR_RE.fullmatch(token)
    ]
    return filtered or [token for token in tokens if token not in RELEASE_NOISE_TOKENS and not YEAR_RE.fullmatch(token)]
