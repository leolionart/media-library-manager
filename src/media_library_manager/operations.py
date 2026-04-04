from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .scanner import companion_files, compute_sha256


ApplyProgressCallback = Callable[[dict[str, Any]], None]


def load_plan(plan_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(plan_path).read_text(encoding="utf-8"))


def apply_plan(
    plan: dict[str, Any],
    *,
    execute: bool = False,
    prune_empty_dirs: bool = False,
    progress_callback: ApplyProgressCallback | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    total_actions = len(plan["actions"])
    progress_summary = {
        "total": total_actions,
        "completed": 0,
        "error": 0,
        "skipped": 0,
        "applied": 0,
        "dry_run": 0,
    }

    for index, action in enumerate(plan["actions"], start=1):
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
                    "mode": "execute" if execute else "dry-run",
                    "summary": progress_summary.copy(),
                }
            )

        if action_type == "review":
            result = {"status": "skipped", "type": action_type, "source": action["source"]}
        elif action_type == "move":
            result = perform_move(action, execute=execute, prune_empty_dirs=prune_empty_dirs)
        elif action_type == "delete":
            result = perform_delete(action, execute=execute, prune_empty_dirs=prune_empty_dirs)
        else:
            result = {"status": "error", "type": action_type, "source": action["source"], "message": "unknown action"}

        results.append(result)
        status = result["status"]
        if status == "skipped":
            progress_summary["skipped"] += 1
        elif status == "error":
            progress_summary["error"] += 1
        elif status == "applied":
            progress_summary["applied"] += 1
            progress_summary["completed"] += 1
        elif status == "dry-run":
            progress_summary["dry_run"] += 1
            progress_summary["completed"] += 1

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
                    "mode": "execute" if execute else "dry-run",
                    "result": result,
                    "summary": progress_summary.copy(),
                }
            )

    return {"summary": summarize_results(results), "results": results}


def perform_move(action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool) -> dict[str, Any]:
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


def perform_delete(action: dict[str, Any], *, execute: bool, prune_empty_dirs: bool) -> dict[str, Any]:
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
    summary = {"applied": 0, "dry-run": 0, "skipped": 0, "error": 0}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary
