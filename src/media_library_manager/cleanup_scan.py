from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .models import MediaFile, RootConfig
from .providers.base import ProviderError
from .providers.radarr import RadarrClient
from .providers.sonarr import SonarrClient
from .scanner import VIDEO_EXTENSIONS, build_folder_media_duplicate_groups, inspect_media_file
from .scanner_storage import LocalPathScannerStorage
from .sync_integrations import build_provider_config


CleanupProgressCallback = Callable[[dict[str, object]], None]


def scan_provider_cleanup(
    integrations: dict[str, Any],
    *,
    providers: list[str] | None = None,
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    requested = [provider for provider in (providers or ["radarr", "sonarr"]) if provider in {"radarr", "sonarr"}]
    if not requested:
        return _build_cleanup_report(providers=[], provider_items=[], files=[], skipped_items=[], errors=[])

    all_roots: list[RootConfig] = []
    provider_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    active_providers: list[str] = []

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
            path = Path(raw_path).expanduser().resolve()
            if not path.exists():
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": str(path), "reason": "path_not_found"}
                )
                continue
            if not path.is_dir():
                skipped_items.append(
                    {"provider": provider, "id": item.get("id"), "title": item.get("title"), "path": str(path), "reason": "path_not_directory"}
                )
                continue
            provider_items.append(
                {
                    "provider": provider,
                    "id": item.get("id"),
                    "title": item.get("title") or path.name,
                    "year": item.get("year"),
                    "path": str(path),
                }
            )
            all_roots.append(
                RootConfig(
                    path=path,
                    label=str(item.get("title") or path.name),
                    priority=100,
                    kind="movie" if provider == "radarr" else "series",
                )
            )

    if progress_callback:
        progress_callback(
            {
                "event": "provider_roots_loaded",
                "providers": active_providers,
                "roots_scanned": len(all_roots),
                "skipped": len(skipped_items),
                "errors": len(errors),
            }
        )

    if not all_roots:
        return _build_cleanup_report(
            providers=active_providers,
            provider_items=provider_items,
            files=[],
            skipped_items=skipped_items,
            errors=errors,
        )

    files = _scan_provider_roots(all_roots, progress_callback=progress_callback, should_cancel=should_cancel)
    return _build_cleanup_report(
        providers=active_providers,
        provider_items=provider_items,
        files=files,
        skipped_items=skipped_items,
        errors=errors,
    )


def rebuild_cleanup_report(existing_report: dict[str, Any], files: list[MediaFile]) -> dict[str, Any]:
    return _build_cleanup_report(
        providers=[str(provider) for provider in existing_report.get("providers", [])],
        provider_items=[item for item in existing_report.get("provider_items", []) if isinstance(item, dict)],
        files=files,
        skipped_items=[item for item in existing_report.get("skipped_items", []) if isinstance(item, dict)],
        errors=[item for item in existing_report.get("errors", []) if isinstance(item, dict)],
    )


def _scan_provider_roots(
    roots: list[RootConfig],
    *,
    progress_callback: CleanupProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[MediaFile]:
    storage = LocalPathScannerStorage()
    files: list[MediaFile] = []
    total_roots = len(roots)
    total_files = 0

    for index, root in enumerate(roots, start=1):
        if should_cancel and should_cancel():
            raise RuntimeError("job cancelled")
        root_file_count = 0
        if progress_callback:
            progress_callback(
                {
                    "event": "root_started",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "total_indexed_files": total_files,
                }
            )
        for entry in storage.iter_video_files(root, allowed_suffixes=VIDEO_EXTENSIONS):
            if should_cancel and should_cancel():
                raise RuntimeError("job cancelled")
            files.append(inspect_media_file(entry, root))
            root_file_count += 1
            total_files += 1
        if progress_callback:
            progress_callback(
                {
                    "event": "root_completed",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "indexed_files": root_file_count,
                    "total_indexed_files": total_files,
                }
            )

    if progress_callback:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": total_roots,
                "total_indexed_files": total_files,
                "exact_duplicate_groups": 0,
                "media_collision_groups": 0,
                "folder_media_duplicate_groups": len(build_folder_media_duplicate_groups(files)),
            }
        )
    return files


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
        provider_item = item_by_path.get(str(group.get("root_path") or ""), {})
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
