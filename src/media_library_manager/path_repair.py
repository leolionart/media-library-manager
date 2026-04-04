from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import RootConfig
from .providers.base import ProviderError
from .providers.radarr import RadarrClient
from .providers.sonarr import SonarrClient
from .storage import StoragePath, default_storage_manager
from .sync_integrations import build_provider_config, normalize_title


YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def scan_provider_path_issues(
    integrations: dict[str, Any],
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    manager = default_storage_manager(lan_connections=lan_connections)
    providers = [provider for provider in ["radarr", "sonarr"] if integrations.get(provider, {}).get("enabled")]
    issues: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_providers = len(providers)

    for index, provider in enumerate(providers, start=1):
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

        issues_before = len(issues)
        for item in items:
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                issues.append(_build_issue(provider, item, reason="missing_path", suggestions=[]))
                continue
            resolved = Path(raw_path).expanduser().resolve()
            if resolved.exists() and resolved.is_dir():
                continue
            suggestions = find_path_repair_suggestions(
                provider=provider,
                item=item,
                roots=roots,
                manager=manager,
            )
            issues.append(
                _build_issue(
                    provider,
                    item,
                    reason="path_not_found" if not resolved.exists() else "path_not_directory",
                    suggestions=suggestions,
                )
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

    with_suggestions = sum(1 for issue in issues if issue.get("suggestions"))
    if progress_callback is not None:
        progress_callback(
            {
                "event": "scan_completed",
                "total_providers": total_providers,
                "issues": len(issues),
                "with_suggestions": with_suggestions,
                "errors": len(errors),
            }
        )

    return {
        "version": 1,
        "summary": {
            "providers": total_providers,
            "issues": len(issues),
            "with_suggestions": with_suggestions,
            "errors": len(errors),
        },
        "issues": issues,
        "errors": errors,
    }


def update_provider_item_path(integrations: dict[str, Any], *, provider: str, item_id: int, new_path: str) -> dict[str, Any]:
    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}

    resolved_path = str(Path(new_path).expanduser().resolve())
    try:
        if provider == "radarr":
            client = RadarrClient(config)
            movie = next((item for item in client.list_movies() if int(item.get("id") or 0) == int(item_id)), None)
            if movie is None:
                return {"status": "error", "message": f"radarr item not found: {item_id}"}
            movie["path"] = resolved_path
            updated = client.update_movie(movie)
            refresh = client.refresh_movie(int(item_id))
        elif provider == "sonarr":
            client = SonarrClient(config)
            series = next((item for item in client.list_series() if int(item.get("id") or 0) == int(item_id)), None)
            if series is None:
                return {"status": "error", "message": f"sonarr item not found: {item_id}"}
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


def delete_provider_item(integrations: dict[str, Any], *, provider: str, item_id: int) -> dict[str, Any]:
    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}

    try:
        if provider == "radarr":
            client = RadarrClient(config)
            result = client.delete_movie(item_id, delete_files=False, add_import_exclusion=False)
        elif provider == "sonarr":
            client = SonarrClient(config)
            result = client.delete_series(item_id, delete_files=False, add_import_exclusion=False)
        else:
            return {"status": "error", "message": f"unsupported provider: {provider}"}
    except ProviderError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "success",
        "provider": provider,
        "item_id": item_id,
        "delete_files": False,
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
    ranked: list[tuple[int, dict[str, Any]]] = []

    for root in _iter_provider_roots(provider, roots):
        root_storage_path = _root_to_storage_path(root)
        ranked.extend(_collect_root_matches(manager, root, root_storage_path, aliases=aliases, year=year, max_depth=max_depth))

    ranked.sort(key=lambda item: (-item[0], item[1]["path"].lower()))
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, candidate in ranked:
        path = candidate["path"]
        if path in seen:
            continue
        seen.add(path)
        suggestions.append({**candidate, "score": score})
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def search_library_paths(
    *,
    provider: str,
    query: str,
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    max_depth: int = 8,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    normalized_query = normalize_title(query)
    if not normalized_query:
        return []
    aliases = [normalized_query]

    manager = default_storage_manager(lan_connections=lan_connections)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for root in _iter_provider_roots(provider, roots):
        root_storage_path = _root_to_storage_path(root)
        ranked.extend(_collect_root_matches(manager, root, root_storage_path, aliases=aliases, year=None, max_depth=max_depth))

    ranked.sort(key=lambda item: (-item[0], item[1]["path"].lower()))
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, candidate in ranked:
        path = candidate["path"]
        if path in seen:
            continue
        seen.add(path)
        results.append({**candidate, "score": score})
        if len(results) >= max_results:
            break
    return results


def _collect_root_matches(manager: Any, root: RootConfig, current: StoragePath, *, aliases: list[str], year: int | None, max_depth: int) -> list[tuple[int, dict[str, Any]]]:
    matches: list[tuple[int, dict[str, Any]]] = []
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
            score = _score_candidate(candidate_name, aliases=aliases, year=year, root_kind=root.kind)
            if score > 0:
                matches.append(
                    (
                        score,
                        {
                            "label": candidate_name,
                            "path": entry.path.normalized_path(),
                            "storage_uri": entry.path.to_uri(),
                            "root_label": root.label,
                            "root_path": str(root.path),
                            "kind": root.kind,
                            "depth": depth + 1,
                        },
                    )
                )
            pending.append((entry.path, depth + 1))
    return matches


def _score_candidate(name: str, *, aliases: list[str], year: int | None, root_kind: str) -> int:
    normalized_name = normalize_title(name)
    aliases = [alias for alias in aliases if alias]
    if not normalized_name or not aliases:
        return 0
    score = max(_score_alias(normalized_name, alias) for alias in aliases)
    if year and str(year) in normalized_name:
        score += 15
    if root_kind != "mixed":
        score += 5
    return score


def _build_issue(provider: str, item: dict[str, Any], *, reason: str, suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"{provider}:{item.get('id')}",
        "provider": provider,
        "item_id": item.get("id"),
        "title": item.get("title"),
        "year": item.get("year"),
        "path": item.get("path"),
        "reason": reason,
        "suggestions": suggestions,
    }


def _list_provider_items(provider: str, config: Any) -> list[dict[str, Any]]:
    if provider == "radarr":
        return RadarrClient(config).list_movies()
    if provider == "sonarr":
        return SonarrClient(config).list_series()
    raise ProviderError(f"unsupported provider: {provider}")


def _root_to_storage_path(root: RootConfig) -> StoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://")):
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
    return matched


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
    if normalized_name == alias:
        return 100
    if normalized_name.startswith(alias):
        return 85
    if alias in normalized_name:
        return 65

    alias_tokens = [token for token in alias.split() if token]
    overlap = sum(1 for token in alias_tokens if token in normalized_name)
    if not overlap:
        return 0

    coverage = overlap / max(1, len(alias_tokens))
    if coverage >= 0.8:
        return 48 + overlap * 6
    if coverage >= 0.6:
        return 34 + overlap * 5
    if overlap >= 2:
        return 20 + overlap * 4
    return 0
