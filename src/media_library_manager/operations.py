from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from .operation_storage import OperationStorageRouter
from .scanner import SIDECAR_EXTENSIONS, companion_files, compute_sha256


ApplyProgressCallback = Callable[[dict[str, Any]], None]
ShouldCancelCallback = Callable[[], bool]


def load_plan(plan_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(plan_path).read_text(encoding="utf-8"))


def apply_plan(
    plan: dict[str, Any],
    *,
    execute: bool = False,
    prune_empty_dirs: bool = False,
    progress_callback: ApplyProgressCallback | None = None,
    storage_router: OperationStorageRouter | None = None,
    should_cancel: ShouldCancelCallback | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    total_actions = len(plan["actions"])
    mode = "apply" if execute else "preview"
    progress_summary = {
        "total": total_actions,
        "completed": 0,
        "error": 0,
        "skipped": 0,
        "applied": 0,
        "dry_run": 0,
    }

    for index, action in enumerate(plan["actions"], start=1):
        if should_cancel and should_cancel():
            return {
                "summary": summarize_results(results),
                "results": results,
                "status": "cancelled",
                "cancelled_at_action": index,
            }
        action_type = action["type"]
        if progress_callback:
            progress_callback(
                {
                    "event": "action_started",
                    "index": index,
                    "total": total_actions,
                    "action_type": action_type,
                    "source": action["source"],
                    "destination": action.get("destination"),
                    "keep_path": action.get("keep_path"),
                    "mode": mode,
                    "summary": progress_summary.copy(),
                }
            )

        if action_type == "review":
            result = {"status": "skipped", "type": action_type, "source": action["source"]}
        elif action_type == "move":
            result = perform_move(action, execute=execute, prune_empty_dirs=prune_empty_dirs, storage_router=storage_router)
        elif action_type == "delete":
            result = perform_delete(action, execute=execute, prune_empty_dirs=prune_empty_dirs, storage_router=storage_router)
        else:
            result = {"status": "error", "type": action_type, "source": action["source"], "message": "unknown action"}

        results.append(result)
        status = result["status"]
        progress_summary["completed"] += 1
        if status == "skipped":
            progress_summary["skipped"] += 1
        elif status == "error":
            progress_summary["error"] += 1
        elif status == "applied":
            progress_summary["applied"] += 1
        elif status == "dry-run":
            progress_summary["dry_run"] += 1

        if progress_callback:
            progress_callback(
                {
                    "event": "action_finished",
                    "index": index,
                    "total": total_actions,
                    "action_type": action_type,
                    "source": action["source"],
                    "destination": action.get("destination"),
                    "keep_path": action.get("keep_path"),
                    "mode": mode,
                    "result": result,
                    "summary": progress_summary.copy(),
                }
            )

    return {"summary": summarize_results(results), "results": results}


def perform_move(
    action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool, storage_router: OperationStorageRouter | None = None
) -> dict[str, Any]:
    if _uses_storage_abstraction(
        action.get("source"),
        action.get("destination"),
        action.get("source_uri"),
        action.get("destination_uri"),
    ):
        return _perform_move_with_storage_router(
            action,
            execute=execute,
            prune_empty_dirs=prune_empty_dirs,
            storage_router=storage_router or OperationStorageRouter(),
        )

    source = Path(action["source"])
    destination = Path(action["destination"])
    bundle = [source, *companion_files(source)]
    operations = []
    for item in bundle:
        destination_item = destination if item == source else destination.with_suffix(item.suffix)
        operations.append({"from": str(item), "to": str(destination_item)})

    if not execute:
        return {"status": "dry-run", "type": "move", "source": str(source), "destination": str(destination), "operations": operations}

    destination.parent.mkdir(parents=True, exist_ok=True)
    for item in bundle:
        destination_item = destination if item == source else destination.with_suffix(item.suffix)
        if destination_item.exists():
            if destination_item.is_file() and item.is_file() and compute_sha256(destination_item) == compute_sha256(item):
                item.unlink()
            else:
                return {
                    "status": "error",
                    "type": "move",
                    "source": str(source),
                    "destination": str(destination),
                    "message": f"destination exists: {destination_item}",
                }
        else:
            item.rename(destination_item)

    if prune_empty_dirs:
        prune_empty_parent_dirs(source.parent, stop_at=Path(action["root_path"]))

    return {"status": "applied", "type": "move", "source": str(source), "destination": str(destination), "operations": operations}


def perform_delete(
    action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool, storage_router: OperationStorageRouter | None = None
) -> dict[str, Any]:
    if _uses_storage_abstraction(action.get("source"), action.get("source_uri")):
        return _perform_delete_with_storage_router(
            action,
            execute=execute,
            prune_empty_dirs=prune_empty_dirs,
            storage_router=storage_router or OperationStorageRouter(),
        )

    source = Path(action["source"])
    bundle = [source, *companion_files(source)]
    if not execute:
        return {
            "status": "dry-run",
            "type": "delete",
            "source": str(source),
            "keep_path": action.get("keep_path"),
            "operations": [{"delete": str(item)} for item in bundle],
        }

    for item in bundle:
        if item.exists():
            item.unlink()

    if prune_empty_dirs:
        prune_empty_parent_dirs(source.parent, stop_at=Path(action["root_path"]))

    return {
        "status": "applied",
        "type": "delete",
        "source": str(source),
        "keep_path": action.get("keep_path"),
        "operations": [{"delete": str(item)} for item in bundle],
    }


def prune_empty_parent_dirs(directory: Path, *, stop_at: Path) -> None:
    current = directory
    stop_at = stop_at.resolve()
    while current.exists() and current != stop_at:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def summarize_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"completed": 0, "applied": 0, "dry-run": 0, "skipped": 0, "error": 0}
    for result in results:
        summary["completed"] += 1
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary


def move_folder(
    source: str | Path,
    destination_parent: str | Path,
    *,
    execute: bool = False,
    storage_router: OperationStorageRouter | None = None,
) -> dict[str, Any]:
    router = storage_router or OperationStorageRouter()
    source_ref, source_error = _parse_storage_path(router, source)
    if source_error:
        return {"status": "error", "message": source_error}
    destination_parent_ref, destination_error = _parse_storage_path(router, destination_parent)
    if destination_error:
        return {"status": "error", "message": destination_error}
    assert source_ref is not None and destination_parent_ref is not None
    router_error = _validate_router_for_storage_paths(router, source_ref, destination_parent_ref)
    if router_error:
        return {"status": "error", "message": router_error}

    source_value = router.stringify(source_ref)
    destination_parent_value = router.stringify(destination_parent_ref)

    try:
        if not router.exists(source_ref):
            return {"status": "error", "message": f"source does not exist: {source_value}"}
        if not router.is_dir(source_ref):
            return {"status": "error", "message": f"source is not a directory: {source_value}"}
        if not router.exists(destination_parent_ref):
            return {"status": "error", "message": f"destination does not exist: {destination_parent_value}"}
        if not router.is_dir(destination_parent_ref):
            return {"status": "error", "message": f"destination is not a directory: {destination_parent_value}"}

        destination_ref = router.join(destination_parent_ref, source_ref.name)
        destination_value = router.stringify(destination_ref)
        if router.exists(destination_ref):
            return {"status": "error", "message": f"destination already exists: {destination_value}"}
        if router.is_relative_to(destination_parent_ref, source_ref):
            return {"status": "error", "message": "destination cannot contain the source folder"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    operations = [{"move_dir": source_value, "to_parent": destination_parent_value, "destination": destination_value}]
    if not execute:
        if router.same_backend_namespace(source_ref, destination_parent_ref):
            return {
                "status": "dry-run",
                "type": "move-folder",
                "source": source_value,
                "destination_parent": destination_parent_value,
                "destination": destination_value,
                "operations": operations,
            }
        return _move_tree_cross_namespace(
            router,
            source_ref,
            destination_ref,
            execute=False,
            operation_type="move-folder",
            destination_parent_value=destination_parent_value,
        )

    try:
        if router.same_backend_namespace(source_ref, destination_ref):
            router.rename(source_ref, destination_ref)
        else:
            return _move_tree_cross_namespace(
                router,
                source_ref,
                destination_ref,
                execute=True,
                operation_type="move-folder",
                destination_parent_value=destination_parent_value,
            )
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "applied",
        "type": "move-folder",
        "source": source_value,
        "destination_parent": destination_parent_value,
        "destination": destination_value,
        "operations": operations,
    }


def move_folder_contents(
    source: str | Path,
    destination: str | Path,
    *,
    execute: bool = False,
    storage_router: OperationStorageRouter | None = None,
) -> dict[str, Any]:
    router = storage_router or OperationStorageRouter()
    source_ref, source_error = _parse_storage_path(router, source)
    if source_error:
        return {"status": "error", "message": source_error}
    destination_ref, destination_error = _parse_storage_path(router, destination)
    if destination_error:
        return {"status": "error", "message": destination_error}
    assert source_ref is not None and destination_ref is not None
    router_error = _validate_router_for_storage_paths(router, source_ref, destination_ref)
    if router_error:
        return {"status": "error", "message": router_error}

    source_value = router.stringify(source_ref)
    destination_value = router.stringify(destination_ref)

    try:
        if not router.exists(source_ref):
            return {"status": "error", "message": f"source does not exist: {source_value}"}
        if not router.is_dir(source_ref):
            return {"status": "error", "message": f"source is not a directory: {source_value}"}
        if not router.exists(destination_ref):
            return {"status": "error", "message": f"destination does not exist: {destination_value}"}
        if not router.is_dir(destination_ref):
            return {"status": "error", "message": f"destination is not a directory: {destination_value}"}
        if router.is_relative_to(destination_ref, source_ref):
            return {"status": "error", "message": "destination cannot be inside the source folder"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    if not router.same_backend_namespace(source_ref, destination_ref):
        return _move_folder_contents_cross_namespace(router, source_ref, destination_ref, execute=execute)

    try:
        items = router.listdir(source_ref)
        operations = [{"move": router.stringify(item), "destination": router.stringify(router.join(destination_ref, item.name))} for item in items]
        for item in items:
            destination_item = router.join(destination_ref, item.name)
            if router.exists(destination_item):
                return {"status": "error", "message": f"destination entry exists: {router.stringify(destination_item)}"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    if not execute:
        return {
            "status": "dry-run",
            "type": "move-folder-contents",
            "source": source_value,
            "destination": destination_value,
            "operations": operations,
        }

    try:
        for item in items:
            router.rename(item, router.join(destination_ref, item.name))
        router.remove_dir_if_empty(source_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "applied",
        "type": "move-folder-contents",
        "source": source_value,
        "destination": destination_value,
        "operations": operations,
    }


def _move_folder_contents_cross_namespace(
    router: OperationStorageRouter,
    source_ref: Any,
    destination_ref: Any,
    *,
    execute: bool,
) -> dict[str, Any]:
    source_value = router.stringify(source_ref)
    destination_value = router.stringify(destination_ref)

    try:
        transfer_items = _collect_cross_namespace_transfer_items(router, source_ref, destination_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    operations = [item["operation"] for item in transfer_items]
    operations.append({"delete_dir": source_value})
    if not execute:
        return {
            "status": "dry-run",
            "type": "move-folder-contents",
            "source": source_value,
            "destination": destination_value,
            "operations": operations,
        }

    try:
        for item in transfer_items:
            if item["kind"] == "dir":
                router.mkdir_parents(item["destination"])
            else:
                parent = router.parent(item["destination"])
                if parent is not None:
                    router.mkdir_parents(parent)
                router.copy_file(item["source"], item["destination"])
        router.delete_tree(source_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "applied",
        "type": "move-folder-contents",
        "source": source_value,
        "destination": destination_value,
        "operations": operations,
    }


def _move_tree_cross_namespace(
    router: OperationStorageRouter,
    source_ref: Any,
    destination_ref: Any,
    *,
    execute: bool,
    operation_type: str,
    destination_parent_value: str | None = None,
) -> dict[str, Any]:
    source_value = router.stringify(source_ref)
    destination_value = router.stringify(destination_ref)

    try:
        if router.exists(destination_ref):
            return {
                "status": "error",
                "type": operation_type,
                "source": source_value,
                "destination": destination_value,
                "message": f"destination already exists: {destination_value}" if operation_type == "move-folder" else f"destination exists: {destination_value}",
            }
        transfer_items = [
            {
                "kind": "dir",
                "source": source_ref,
                "destination": destination_ref,
                "operation": {"mkdir": destination_value},
            },
            *_collect_cross_namespace_transfer_items(router, source_ref, destination_ref),
        ]
    except ValueError as exc:
        return {"status": "error", "type": operation_type, "source": source_value, "destination": destination_value, "message": str(exc)}

    operations = [item["operation"] for item in transfer_items]
    operations.append({"delete_dir": source_value})
    if not execute:
        payload = {
            "status": "dry-run",
            "type": operation_type,
            "source": source_value,
            "destination": destination_value,
            "operations": operations,
        }
        if destination_parent_value is not None:
            payload["destination_parent"] = destination_parent_value
        return payload

    try:
        for item in transfer_items:
            if item["kind"] == "dir":
                router.mkdir_parents(item["destination"])
            else:
                parent = router.parent(item["destination"])
                if parent is not None:
                    router.mkdir_parents(parent)
                router.copy_file(item["source"], item["destination"])
        router.delete_tree(source_ref)
    except ValueError as exc:
        return {"status": "error", "type": operation_type, "source": source_value, "destination": destination_value, "message": str(exc)}

    payload = {
        "status": "applied",
        "type": operation_type,
        "source": source_value,
        "destination": destination_value,
        "operations": operations,
    }
    if destination_parent_value is not None:
        payload["destination_parent"] = destination_parent_value
    return payload


def _collect_cross_namespace_transfer_items(router: OperationStorageRouter, source_ref: Any, destination_ref: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for child in router.listdir(source_ref):
        destination_child = router.join(destination_ref, child.name)
        if router.exists(destination_child):
            raise ValueError(f"destination entry exists: {router.stringify(destination_child)}")
        if router.is_dir(child):
            items.append(
                {
                    "kind": "dir",
                    "source": child,
                    "destination": destination_child,
                    "operation": {"mkdir": router.stringify(destination_child)},
                }
            )
            items.extend(_collect_cross_namespace_transfer_items(router, child, destination_child))
            continue
        items.append(
            {
                "kind": "file",
                "source": child,
                "destination": destination_child,
                "operation": {"copy": router.stringify(child), "destination": router.stringify(destination_child)},
            }
        )
    return items


def delete_folder(path: str | Path, *, execute: bool = False, storage_router: OperationStorageRouter | None = None) -> dict[str, Any]:
    router = storage_router or OperationStorageRouter()
    target_ref, parse_error = _parse_storage_path(router, path)
    if parse_error:
        return {"status": "error", "message": parse_error}
    assert target_ref is not None

    target_value = router.stringify(target_ref)
    try:
        if not router.exists(target_ref):
            return {"status": "error", "message": f"path does not exist: {target_value}"}
        if not router.is_dir(target_ref):
            return {"status": "error", "message": f"path is not a directory: {target_value}"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    operations = [{"delete_dir": target_value}]
    if not execute:
        return {"status": "dry-run", "type": "delete-folder", "path": target_value, "operations": operations}

    try:
        router.delete_tree(target_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "applied", "type": "delete-folder", "path": target_value, "operations": operations}


def delete_media_file(
    path: str | Path,
    *,
    storage_uri: str = "",
    root_path: str | Path | None = None,
    root_storage_uri: str = "",
    execute: bool = False,
    prune_empty_dirs: bool = True,
    storage_router: OperationStorageRouter | None = None,
) -> dict[str, Any]:
    router = storage_router or OperationStorageRouter()
    target_input = storage_uri or path
    target_ref, parse_error = _parse_storage_path(router, target_input)
    if parse_error:
        return {"status": "error", "message": parse_error}
    assert target_ref is not None

    target_value = router.stringify(target_ref)
    try:
        if getattr(target_ref, "backend", "") == "local":
            if not router.exists(target_ref):
                return {"status": "error", "message": f"path does not exist: {target_value}"}
            if not router.is_file(target_ref):
                return {"status": "error", "message": f"path is not a file: {target_value}"}
        else:
            if not router.is_file(target_ref):
                if router.exists(target_ref):
                    return {"status": "error", "message": f"path is not a file: {target_value}"}
                return {"status": "error", "message": f"path does not exist: {target_value}"}
        bundle = _collect_media_file_bundle(router, target_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    operations = [{"delete": router.stringify(item)} for item in bundle]
    if not execute:
        return {"status": "dry-run", "type": "delete-media-file", "path": target_value, "operations": operations}

    try:
        for item in bundle:
            if router.exists(item):
                router.delete_file(item)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    root_value = root_storage_uri or (str(root_path) if root_path else "")
    if prune_empty_dirs and root_value:
        _prune_empty_parent_dirs_with_storage_router(router, target_ref, root_value)

    return {"status": "applied", "type": "delete-media-file", "path": target_value, "operations": operations}


def delete_file(path: str | Path, *, execute: bool = False, storage_router: OperationStorageRouter | None = None) -> dict[str, Any]:
    router = storage_router or OperationStorageRouter()
    target_ref, parse_error = _parse_storage_path(router, path)
    if parse_error:
        return {"status": "error", "message": parse_error}
    assert target_ref is not None

    target_value = router.stringify(target_ref)
    try:
        if getattr(target_ref, "backend", "") == "local":
            if not router.exists(target_ref):
                return {"status": "error", "message": f"path does not exist: {target_value}"}
            if not router.is_file(target_ref):
                return {"status": "error", "message": f"path is not a file: {target_value}"}
        else:
            if not router.is_file(target_ref):
                if router.exists(target_ref):
                    return {"status": "error", "message": f"path is not a file: {target_value}"}
                return {"status": "error", "message": f"path does not exist: {target_value}"}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    operations = [{"delete": target_value}]
    if not execute:
        return {"status": "dry-run", "type": "delete-file", "path": target_value, "operations": operations}

    try:
        router.delete_file(target_ref)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "applied", "type": "delete-file", "path": target_value, "operations": operations}


def _uses_storage_abstraction(*values: object) -> bool:
    return any(str(value or "").strip().startswith(("smb://", "rclone://")) for value in values)


def _validate_router_for_storage_paths(router: OperationStorageRouter, *paths: object) -> str | None:
    if router.smb_connection_resolver is None and any(getattr(path, "backend", "") == "smb" for path in paths):
        return "SMB operation requires a connection resolver"
    return None


def _parse_storage_path(router: OperationStorageRouter, value: str | Path) -> tuple[Any | None, str | None]:
    try:
        return router.parse_storage_path(value), None
    except ValueError as exc:
        return None, str(exc)


def _collect_media_file_bundle(storage_router: OperationStorageRouter, source_ref: Any) -> list[Any]:
    if getattr(source_ref, "backend", "") == "local":
        assert source_ref.local_path is not None
        return [source_ref, *[storage_router.parse_storage_path(item) for item in companion_files(source_ref.local_path)]]

    parent_ref = storage_router.parent(source_ref)
    if parent_ref is None:
        return [source_ref]
    source_name = source_ref.name
    source_stem = Path(source_name).stem
    companions = [source_ref]
    for item in storage_router.listdir(parent_ref):
        if item == source_ref or not storage_router.is_file(item):
            continue
        if Path(item.name).stem != source_stem:
            continue
        if Path(item.name).suffix.lower() in SIDECAR_EXTENSIONS:
            companions.append(item)
    return sorted(companions, key=storage_router.stringify)


def _perform_move_with_storage_router(
    action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool, storage_router: OperationStorageRouter
) -> dict[str, Any]:
    source_input = str(action.get("source_uri") or action["source"])
    destination_input = str(action.get("destination_uri") or action["destination"])
    source_ref, source_error = _parse_storage_path(storage_router, source_input)
    if source_error:
        return {"status": "error", "type": "move", "source": str(action["source"]), "message": source_error}
    destination_ref, destination_error = _parse_storage_path(storage_router, destination_input)
    if destination_error:
        return {"status": "error", "type": "move", "source": str(action["source"]), "message": destination_error}
    assert source_ref is not None and destination_ref is not None

    source_value = storage_router.stringify(source_ref)
    destination_value = storage_router.stringify(destination_ref)
    try:
        destination_parent = storage_router.parent(destination_ref)
        if destination_parent is not None and not storage_router.exists(destination_parent):
            storage_router.mkdir_parents(destination_parent)
    except ValueError as exc:
        return {"status": "error", "type": "move", "source": source_value, "destination": destination_value, "message": str(exc)}

    operations = (
        [{"from": source_value, "to": destination_value}]
        if storage_router.same_backend_namespace(source_ref, destination_ref)
        else [{"copy": source_value, "destination": destination_value}, {"delete": source_value}]
    )
    if not execute:
        return {"status": "dry-run", "type": "move", "source": source_value, "destination": destination_value, "operations": operations}

    try:
        if storage_router.exists(destination_ref):
            return {"status": "error", "type": "move", "source": source_value, "destination": destination_value, "message": f"destination exists: {destination_value}"}
    except ValueError as exc:
        return {"status": "error", "type": "move", "source": source_value, "destination": destination_value, "message": str(exc)}

    try:
        if storage_router.same_backend_namespace(source_ref, destination_ref):
            storage_router.rename(source_ref, destination_ref)
        else:
            storage_router.copy_file(source_ref, destination_ref)
            storage_router.delete_file(source_ref)
    except ValueError as exc:
        return {"status": "error", "type": "move", "source": source_value, "destination": destination_value, "message": str(exc)}

    if prune_empty_dirs:
        root_value = action.get("root_path")
        if root_value:
            _prune_empty_parent_dirs_with_storage_router(storage_router, source_ref, str(root_value))

    return {"status": "applied", "type": "move", "source": source_value, "destination": destination_value, "operations": operations}


def _perform_delete_with_storage_router(
    action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool, storage_router: OperationStorageRouter
) -> dict[str, Any]:
    source_input = str(action.get("source_uri") or action["source"])
    source_ref, source_error = _parse_storage_path(storage_router, source_input)
    if source_error:
        return {"status": "error", "type": "delete", "source": str(action["source"]), "message": source_error}
    assert source_ref is not None
    source_value = storage_router.stringify(source_ref)

    try:
        if not storage_router.exists(source_ref):
            return {
                "status": "applied" if execute else "dry-run",
                "type": "delete",
                "source": source_value,
                "keep_path": action.get("keep_path"),
                "operations": [{"delete": source_value}],
            }
    except ValueError as exc:
        return {"status": "error", "type": "delete", "source": source_value, "message": str(exc)}

    operations = [{"delete": source_value}]
    if not execute:
        return {"status": "dry-run", "type": "delete", "source": source_value, "keep_path": action.get("keep_path"), "operations": operations}

    try:
        if storage_router.is_dir(source_ref):
            storage_router.delete_tree(source_ref)
        else:
            storage_router.delete_file(source_ref)
    except ValueError as exc:
        return {"status": "error", "type": "delete", "source": source_value, "message": str(exc)}

    if prune_empty_dirs:
        root_value = action.get("root_path")
        if root_value:
            _prune_empty_parent_dirs_with_storage_router(storage_router, source_ref, str(root_value))

    return {"status": "applied", "type": "delete", "source": source_value, "keep_path": action.get("keep_path"), "operations": operations}


def _prune_empty_parent_dirs_with_storage_router(router: OperationStorageRouter, source_ref: Any, root_value: str) -> None:
    root_ref, root_error = _parse_storage_path(router, root_value)
    if root_error or root_ref is None:
        return
    current = router.parent(source_ref)
    while current is not None and router.same_backend_namespace(current, root_ref) and current != root_ref:
        removed = router.remove_dir_if_empty(current)
        if not removed:
            break
        current = router.parent(current)
