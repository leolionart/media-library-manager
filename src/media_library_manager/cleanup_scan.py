from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .folder_index import build_folder_index_lookup as build_shared_folder_index_lookup
from .folder_index import media_files_from_index_rows, validate_folder_index_report
from .models import MediaFile, RootConfig
from .provider_path_resolution import map_provider_directory
from .providers.base import ProviderError
from .providers.radarr import RadarrClient
from .providers.sonarr import SonarrClient
from .scanner import build_folder_media_duplicate_groups
from .sync_integrations import build_provider_config


CleanupProgressCallback = Callable[[dict[str, object]], None]
MIN_CLEANUP_FOLDER_INDEX_VERSION = 2


from .operation_storage import OperationStorageRouter


def scan_provider_cleanup(
    integrations: dict[str, Any],
    *,
    providers: list[str] | None = None,
    roots: list[RootConfig] | None = None,
    folder_index_report: dict[str, Any] | None = None,
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    start_root_index: int = 1,
    storage_router: OperationStorageRouter | None = None,
) -> dict[str, Any]:
    if storage_router:
        storage_router.clear_cache()
    requested = [provider for provider in (providers or ["radarr", "sonarr"]) if provider in {"radarr", "sonarr"}]
    if not requested:
        return _build_cleanup_report(providers=[], provider_items=[], files=[], skipped_items=[], errors=[])
    cache_error = _validate_cleanup_folder_index(folder_index_report)
    if cache_error:
        raise ValueError(cache_error)

    files: list[MediaFile] = []
    provider_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    active_providers: list[str] = []
    connected_roots = roots or []
    folder_index_lookup = _build_folder_index_lookup(folder_index_report)
    total_files = 0
    skipped_ghost_files = 0

    for provider in requested:
        config = build_provider_config(integrations.get(provider, {}))
        if not config.enabled:
            skipped_items.append({"provider": provider, "reason": "provider_disabled"})
            continue
        try:
            items = _list_provider_items(provider, config)
            active_providers.append(provider)
        except ProviderError as exc:
            errors.append({"provider": provider, "message": str(exc)})
            continue

        for item in items:
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            raw_path = str(item.get("path") or "").strip()
            if not raw_path:
                skipped_items.append({"provider": provider, "id": item.get("id"), "title": item.get("title"), "reason": "missing_path"})
                continue
            resolved, status = _resolve_provider_directory_from_cache(raw_path=raw_path, roots=connected_roots)
            if resolved is None:
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": raw_path, "reason": status}
                )
                continue
            folder_rows = _lookup_folder_index_rows(folder_index_lookup, resolved=resolved)
            if not folder_rows:
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": raw_path, "reason": "folder_index_miss"}
                )
                continue
            provider_items.append(
                {
                    "provider": provider,
                    "id": item.get("id"),
                    "title": item.get("title") or resolved.path.name,
                    "year": item.get("year"),
                    "path": str(resolved.path),
                    "provider_path": raw_path,
                    "storage_uri": resolved.storage_uri,
                }
            )
            root = RootConfig(
                path=resolved.path,
                label=str(item.get("title") or resolved.path.name),
                priority=100,
                kind="movie" if provider == "radarr" else "series",
                connection_id=resolved.connection_id,
                connection_label=resolved.connection_label,
                storage_uri=resolved.storage_uri,
                share_name=resolved.share_name,
            )
            cached_files = media_files_from_index_rows(folder_rows, roots=[root], force_root=root)

            # Verify files existence to avoid "ghost" duplicates from stale cache.
            # We check both local and remote files. 
            # For remote (rclone), we use the router to probe existence which is optimized in _rclone_entry.
            verified_files: list[MediaFile] = []
            for f in cached_files:
                if should_cancel and should_cancel():
                    raise RuntimeError("job cancelled")

                if not f.storage_uri: # Local file
                    if storage_router and not f.path.exists():
                        skipped_ghost_files += 1
                        continue
                else: # Remote file (rclone or smb)
                    # We use a router to check if the file really exists
                    # This might be slightly slow for rclone but necessary for accuracy
                    if storage_router and not storage_router.is_file(f.storage_uri):
                        skipped_ghost_files += 1
                        continue
                
                verified_files.append(f)
            
            files.extend(verified_files)
            total_files += len(verified_files)
            if progress_callback:
                progress_callback(
                    {
                        "event": "root_completed",
                        "index": len(provider_items),
                        "total_roots": len(provider_items),
                        "root_label": root.label,
                        "root_path": str(root.path),
                        "indexed_files": len(verified_files),
                        "total_indexed_files": total_files,
                    }
                )

    if progress_callback:
        progress_callback(
            {
                "event": "provider_roots_loaded",
                "providers": active_providers,
                "roots_scanned": len(provider_items),
                "skipped": len(skipped_items),
                "ghost_files_skipped": skipped_ghost_files,
                "errors": len(errors),
            }
        )
    if progress_callback:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": len(provider_items),
                "total_indexed_files": len(files),
                "exact_duplicate_groups": 0,
                "media_collision_groups": 0,
                "folder_media_duplicate_groups": len(build_folder_media_duplicate_groups(files)),
            }
        )
    return _build_cleanup_report(
        providers=active_providers,
        provider_items=provider_items,
        files=files,
        skipped_items=skipped_items,
        errors=errors,
    )


def _validate_cleanup_folder_index(report: dict[str, Any] | None) -> str | None:
    return validate_folder_index_report(
        report,
        required_capabilities=["video_files"],
        minimum_version=MIN_CLEANUP_FOLDER_INDEX_VERSION,
    )


def _build_folder_index_lookup(report: dict[str, Any] | None) -> dict[str, Any]:
    return build_shared_folder_index_lookup(report)


def _resolve_provider_directory_from_cache(*, raw_path: str, roots: list[RootConfig]) -> tuple[Any | None, str]:
    mapped = map_provider_directory(raw_path=raw_path, roots=roots)
    if mapped is not None:
        return mapped, "ok"
    local_path = Path(str(raw_path or "")).expanduser().resolve()
    if local_path.exists() and not local_path.is_dir():
        return None, "path_not_directory"
    return None, "path_not_found"


def _lookup_folder_index_rows(folder_index_lookup: dict[str, Any], *, resolved: Any) -> list[dict[str, Any]]:
    direct_match: dict[str, Any] | None = None
    storage_uri = str(resolved.storage_uri or "")
    if storage_uri:
        direct_match = folder_index_lookup["by_storage_uri"].get(storage_uri)
    if direct_match is None:
        direct_match = folder_index_lookup["by_path"].get(str(resolved.path))
    if direct_match is None:
        return []

    resolved_path = Path(str(resolved.path))
    matched: list[dict[str, Any]] = []
    for item in folder_index_lookup.get("items", []):
        if not isinstance(item, dict):
            continue
        item_path_text = str(item.get("path") or "").strip()
        if not item_path_text:
            continue
        item_path = Path(item_path_text)
        if item_path == resolved_path or item_path.is_relative_to(resolved_path):
            matched.append(item)
    matched.sort(key=lambda item: (int(item.get("depth") or 0), str(item.get("path") or "").lower()))
    return matched


def rebuild_cleanup_report(existing_report: dict[str, Any], files: list[MediaFile]) -> dict[str, Any]:
    return _build_cleanup_report(
        providers=[str(provider) for provider in existing_report.get("providers", [])],
        provider_items=[item for item in existing_report.get("provider_items", []) if isinstance(item, dict)],
        files=files,
        skipped_items=[item for item in existing_report.get("skipped_items", []) if isinstance(item, dict)],
        errors=[item for item in existing_report.get("errors", []) if isinstance(item, dict)],
    )


def _build_cleanup_report(
    *,
    providers: list[str],
    provider_items: list[dict[str, Any]],
    files: list[MediaFile],
    skipped_items: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = _attach_group_metadata(build_folder_media_duplicate_groups(files), provider_items)
    return {
        "version": 1,
        "providers": providers,
        "provider_items": provider_items,
        "summary": {
            "providers": len(providers),
            "roots_scanned": len(provider_items),
            "indexed_files": len(files),
            "folder_media_duplicate_groups": len(groups),
            "groups": len(groups),
            "skipped": len(skipped_items),
            "errors": len(errors),
        },
        "files": [item.to_dict() for item in files],
        "folder_media_duplicates": groups,
        "groups": groups,
        "skipped_items": skipped_items,
        "errors": errors,
    }


def _list_provider_items(provider: str, config: Any) -> list[dict[str, Any]]:
    if provider == "radarr":
        return RadarrClient(config).list_movies()
    if provider == "sonarr":
        return SonarrClient(config).list_series()
    raise ProviderError(f"unsupported provider: {provider}")


def _attach_group_metadata(groups: list[dict[str, Any]], provider_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_by_path = {str(item.get("path") or ""): item for item in provider_items}
    attached: list[dict[str, Any]] = []
    for group in groups:
        root_path = str(group.get("root_path") or "")
        provider_item = item_by_path.get(root_path)
        if provider_item is None:
            provider_item = next((item for item in provider_items if root_path.startswith(str(item.get("path") or ""))), {})
        attached.append(
            {
                **group,
                "id": f"{group.get('media_key')}::{group.get('folder_path')}",
                "provider": provider_item.get("provider"),
                "provider_item_id": provider_item.get("id"),
                "provider_item_title": provider_item.get("title"),
                "provider_item_year": provider_item.get("year"),
                "provider_item_path": provider_item.get("path"),
            }
        )
    return attached
