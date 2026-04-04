from __future__ import annotations

import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .browser import browse_path, list_mounts
from .models import LibraryTargets, RootConfig
from .network import discover_lan_devices
from .operations import apply_plan
from .planner import load_report, plan_actions
from .scanner import scan_roots
from .state import StateStore
from .sync_integrations import default_integrations, sync_after_apply, test_integrations


PLAN_PROGRESS_TOTAL = 3


def run_dashboard(*, host: str, port: int, state_file: Path) -> None:
    store = StateStore(state_file)
    server = ThreadingHTTPServer((host, port), lambda *args, **kwargs: DashboardHandler(*args, store=store, **kwargs))
    print(f"dashboard listening on http://{host}:{port}")
    server.serve_forever()


class DashboardHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, store: StateStore, **kwargs):
        self.store = store
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.svg":
            self._serve_static("favicon.svg", "image/svg+xml")
            return
        if parsed.path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/state":
            self._send_json(self.store.api_payload())
            return
        if parsed.path == "/api/process":
            self._send_json({"current_job": self.store.load_current_job()})
            return
        if parsed.path == "/api/system/mounts":
            self._send_json({"mounts": [mount.to_dict() for mount in list_mounts()]})
            return
        if parsed.path == "/api/lan/discover":
            self._send_json(discover_lan_devices())
            return
        if parsed.path == "/api/browse":
            params = parse_qs(parsed.query)
            requested_path = params.get("path", [None])[0]
            try:
                self._send_json(browse_path(requested_path))
            except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/roots":
            payload = self._read_json()
            root = normalize_root_payload(payload)
            if not root.path.is_dir():
                self._send_json({"error": f"path is not a directory: {root.path}"}, status=HTTPStatus.BAD_REQUEST)
                return
            self.store.add_root(root)
            self.store.append_activity(
                kind="config",
                status="success",
                message="Added scan root.",
                details={
                    "label": root.label,
                    "path": str(root.path),
                    "priority": root.priority,
                    "kind": root.kind,
                },
            )
            self._send_json(self.store.api_payload(), status=HTTPStatus.CREATED)
            return

        if parsed.path == "/api/targets":
            payload = self._read_json()
            targets = LibraryTargets(
                movie_root=normalize_optional_path(payload.get("movie_root")),
                series_root=normalize_optional_path(payload.get("series_root")),
                review_root=normalize_optional_path(payload.get("review_root")),
            )
            self.store.save_targets(targets)
            self.store.append_activity(
                kind="config",
                status="success",
                message="Saved canonical targets.",
                details={
                    "movie_root": str(targets.movie_root) if targets.movie_root else None,
                    "series_root": str(targets.series_root) if targets.series_root else None,
                    "review_root": str(targets.review_root) if targets.review_root else None,
                },
            )
            self._send_json(self.store.api_payload())
            return

        if parsed.path == "/api/integrations":
            payload = self._read_json()
            integrations = normalize_integrations_payload(payload)
            self.store.save_integrations(integrations)
            self.store.append_activity(
                kind="integration",
                status="success",
                message="Saved Radarr and Sonarr integration settings.",
                details={
                    "radarr_enabled": integrations["radarr"]["enabled"],
                    "sonarr_enabled": integrations["sonarr"]["enabled"],
                    "sync_options": integrations["sync_options"],
                },
            )
            self._send_json(self.store.api_payload())
            return

        if parsed.path == "/api/integrations/test":
            payload = self._read_json()
            integrations = normalize_integrations_payload(payload) if payload else self.store.load_integrations()
            results = test_integrations(integrations)
            status = "success" if all(item.get("status") != "error" for item in results.values()) else "error"
            self.store.append_activity(
                kind="integration",
                status=status,
                message="Integration connectivity test finished.",
                details={"results": results},
            )
            self._send_json({"results": results})
            return

        if parsed.path == "/api/sync":
            plan = self.store.load_plan()
            apply_result = self.store.load_apply_result()
            if plan is None or apply_result is None:
                self.store.append_activity(
                    kind="integration",
                    status="error",
                    message="Manual sync failed because plan/apply result is missing.",
                    details={"error": "plan and apply result are required before sync"},
                )
                self._send_json({"error": "plan and apply result are required before sync"}, status=HTTPStatus.BAD_REQUEST)
                return
            integrations = self.store.load_integrations()
            sync_result = sync_after_apply(plan=plan, apply_result=apply_result, integrations=integrations)
            sync_result["generated_at"] = now_iso()
            self.store.save_sync_result(sync_result)
            self.store.append_activity(
                kind="integration",
                status="success" if sync_result.get("status") != "error" else "error",
                message="Manual Radarr/Sonarr sync completed.",
                details=sync_result,
            )
            self._send_json(sync_result)
            return

        if parsed.path == "/api/scan":
            roots = self.store.list_roots()
            if not roots:
                self.store.append_activity(
                    kind="scan",
                    status="error",
                    message="Scan failed because no roots are configured.",
                    details={"error": "no roots configured"},
                )
                self._send_json({"error": "no roots configured"}, status=HTTPStatus.BAD_REQUEST)
                return

            roots_summary = summarize_roots(roots)
            job_details = {"root_count": len(roots), "roots": roots_summary}
            self.store.start_job(
                kind="scan",
                message="Started library scan.",
                summary={"total": len(roots), "completed": 0},
                details=job_details,
            )
            self.store.append_activity(
                kind="scan",
                status="running",
                message="Started library scan.",
                details=job_details,
            )

            try:
                report = scan_roots(roots, progress_callback=self._scan_progress_callback).to_dict()
            except Exception as exc:
                error_details = {"error": str(exc), **job_details}
                self.store.finish_job(status="error", message="Library scan failed.", details=error_details)
                self.store.append_activity(
                    kind="scan",
                    status="error",
                    message="Library scan failed.",
                    details=error_details,
                )
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            report["generated_at"] = now_iso()
            self.store.save_report(report)
            success_details = {
                "summary": report.get("summary", {}),
                **job_details,
            }
            self.store.finish_job(
                status="success",
                message="Library scan completed.",
                details=success_details,
                summary={"total": len(roots), "completed": len(roots), "indexed_files": report.get("summary", {}).get("files", 0)},
            )
            self.store.append_activity(
                kind="scan",
                status="success",
                message="Library scan completed.",
                details=success_details,
            )
            self._send_json(report)
            return

        if parsed.path == "/api/plan":
            payload = self._read_json()
            report_data = self.store.load_report()
            if report_data is None:
                self.store.append_activity(
                    kind="plan",
                    status="error",
                    message="Plan build failed because no scan report exists.",
                    details={"error": "no report available, run scan first"},
                )
                self._send_json({"error": "no report available, run scan first"}, status=HTTPStatus.BAD_REQUEST)
                return

            delete_lower_quality = bool(payload.get("delete_lower_quality"))
            job_details = {"delete_lower_quality": delete_lower_quality}
            self.store.start_job(
                kind="plan",
                message="Started action plan build.",
                summary={"total": PLAN_PROGRESS_TOTAL, "completed": 0},
                details=job_details,
            )
            self.store.append_activity(
                kind="plan",
                status="running",
                message="Started action plan build.",
                details=job_details,
            )

            try:
                self.store.append_job_log(level="info", message="Loading scan report snapshot.")
                self.store.update_job_progress({"total": PLAN_PROGRESS_TOTAL, "completed": 1})
                report = load_report(self.store.report_file)
                self.store.append_job_log(level="info", message="Building action plan from report.")
                plan = plan_actions(
                    report,
                    self.store.load_targets(),
                    delete_lower_quality=delete_lower_quality,
                )
                self.store.update_job_progress({"total": PLAN_PROGRESS_TOTAL, "completed": 2})
            except Exception as exc:
                error_details = {"error": str(exc), **job_details}
                self.store.finish_job(status="error", message="Action plan build failed.", details=error_details)
                self.store.append_activity(
                    kind="plan",
                    status="error",
                    message="Action plan build failed.",
                    details=error_details,
                )
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            plan["generated_at"] = now_iso()
            self.store.save_plan(plan)
            success_details = {
                "summary": plan.get("summary", {}),
                "delete_lower_quality": delete_lower_quality,
                "preview": preview_actions(plan.get("actions", [])),
            }
            self.store.finish_job(
                status="success",
                message="Action plan created.",
                details=success_details,
                summary={
                    "total": PLAN_PROGRESS_TOTAL,
                    "completed": PLAN_PROGRESS_TOTAL,
                    "actions": len(plan.get("actions", [])),
                },
            )
            self.store.append_activity(
                kind="plan",
                status="success",
                message="Action plan created.",
                details=success_details,
            )
            self._send_json(plan)
            return

        if parsed.path == "/api/apply":
            payload = self._read_json()
            plan = self.store.load_plan()
            if plan is None:
                self.store.append_activity(
                    kind="apply",
                    status="error",
                    message="Apply failed because no plan exists.",
                    details={"error": "no plan available, build plan first"},
                )
                self._send_json({"error": "no plan available, build plan first"}, status=HTTPStatus.BAD_REQUEST)
                return

            execute = bool(payload.get("execute"))
            prune_empty_dirs = bool(payload.get("prune_empty_dirs"))
            action_count = len(plan.get("actions", []))
            job_details = {
                "mode": "execute" if execute else "dry-run",
                "prune_empty_dirs": prune_empty_dirs,
                "action_count": action_count,
            }
            self.store.start_job(
                kind="apply",
                message=f"Started {'execute' if execute else 'dry-run'} apply.",
                summary={"total": action_count, "completed": 0, "error": 0, "skipped": 0, "applied": 0, "dry_run": 0},
                details=job_details,
            )
            self.store.append_activity(
                kind="apply",
                status="running",
                message=f"Started {'execute' if execute else 'dry-run'} apply.",
                details=job_details,
            )

            try:
                result = apply_plan(
                    plan,
                    execute=execute,
                    prune_empty_dirs=prune_empty_dirs,
                    progress_callback=self._apply_progress_callback,
                )
            except Exception as exc:
                error_details = {"error": str(exc), **job_details}
                self.store.finish_job(status="error", message="Plan apply failed.", details=error_details)
                self.store.append_activity(
                    kind="apply",
                    status="error",
                    message="Plan apply failed.",
                    details=error_details,
                )
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            result["generated_at"] = now_iso()
            result["mode"] = "execute" if execute else "dry-run"
            if execute:
                self.store.append_job_log(level="info", message="Syncing Radarr and Sonarr after apply.")
                result["integration_sync"] = sync_after_apply(
                    plan=plan,
                    apply_result=result,
                    integrations=self.store.load_integrations(),
                )
                result["integration_sync"]["generated_at"] = now_iso()
                self.store.save_sync_result(result["integration_sync"])
                self.store.append_job_log(
                    level="info" if result["integration_sync"].get("status") != "error" else "error",
                    message="Integration sync finished.",
                    details={"status": result["integration_sync"].get("status"), "summary": result["integration_sync"].get("summary", {})},
                )
            self.store.save_apply_result(result)
            success_details = {
                "mode": result["mode"],
                "prune_empty_dirs": prune_empty_dirs,
                "summary": result.get("summary", {}),
                "integration_sync": result.get("integration_sync", {}),
                "preview": preview_results(result.get("results", [])),
            }
            self.store.finish_job(
                status="success",
                message=f"{'Execute' if execute else 'Dry-run'} apply completed.",
                details=success_details,
                summary={"total": action_count, **summarize_apply_job(result.get("results", []))},
            )
            self.store.append_activity(
                kind="apply",
                status="success",
                message=f"{'Execute' if execute else 'Dry-run'} apply completed.",
                details=success_details,
            )
            self._send_json(result)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/roots":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        params = parse_qs(parsed.query)
        path_value = params.get("path", [None])[0]
        if not path_value:
            self._send_json({"error": "missing path query parameter"}, status=HTTPStatus.BAD_REQUEST)
            return
        self.store.remove_root(path_value)
        self.store.append_activity(
            kind="config",
            status="success",
            message="Removed scan root.",
            details={"path": str(Path(path_value).expanduser().resolve())},
        )
        self._send_json(self.store.api_payload())

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_static(self, file_name: str, content_type: str) -> None:
        content = resources.files("media_library_manager").joinpath("static", file_name).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _scan_progress_callback(self, event: dict[str, object]) -> None:
        event_name = event.get("event")
        if event_name == "root_started":
            self.store.append_job_log(
                level="info",
                message=f"Scanning root {event['index']}/{event['total_roots']}: {event['root_label']}",
                details={"path": event.get("root_path")},
            )
            self.store.update_job_progress({"total": int(event["total_roots"]), "completed": max(int(event["index"]) - 1, 0)})
            return
        if event_name == "root_completed":
            self.store.append_job_log(
                level="info",
                message=f"Finished root {event['index']}/{event['total_roots']}: {event['root_label']}",
                details={
                    "path": event.get("root_path"),
                    "indexed_files": int(event.get("indexed_files", 0)),
                    "total_indexed_files": int(event.get("total_indexed_files", 0)),
                },
            )
            self.store.update_job_progress(
                {
                    "total": int(event["total_roots"]),
                    "completed": int(event["index"]),
                    "indexed_files": int(event.get("total_indexed_files", 0)),
                }
            )
            return
        if event_name == "scan_completed":
            self.store.append_job_log(
                level="info",
                message="Finished duplicate analysis.",
                details={
                    "indexed_files": int(event.get("total_indexed_files", 0)),
                    "exact_duplicate_groups": int(event.get("exact_duplicate_groups", 0)),
                    "media_collision_groups": int(event.get("media_collision_groups", 0)),
                },
            )

    def _apply_progress_callback(self, event: dict[str, Any]) -> None:
        event_name = event.get("event")
        summary = dict(event.get("summary", {}))
        summary["total"] = int(event.get("total", summary.get("total", 0)))
        if event_name == "action_started":
            self.store.append_job_log(
                level="info",
                message=f"Processing {event.get('action_type')} {event.get('index')}/{event.get('total')}",
                details={
                    "source": event.get("source"),
                    "destination": event.get("destination"),
                    "keep_path": event.get("keep_path"),
                    "mode": event.get("mode"),
                },
            )
            self.store.update_job_progress(summary)
            return
        if event_name == "action_finished":
            result = event.get("result", {})
            self.store.append_job_log(
                level="error" if result.get("status") == "error" else "info",
                message=f"Finished {event.get('action_type')} {event.get('index')}/{event.get('total')} with status {result.get('status')}",
                details={
                    "source": result.get("source"),
                    "destination": result.get("destination"),
                    "keep_path": result.get("keep_path"),
                    "message": result.get("message"),
                },
            )
            self.store.update_job_progress(summary)



def normalize_root_payload(payload: dict) -> RootConfig:
    path = Path(payload["path"]).expanduser().resolve()
    return RootConfig(
        path=path,
        label=(payload.get("label") or path.name).strip(),
        priority=int(payload.get("priority", 50)),
        kind=(payload.get("kind") or "mixed").strip() or "mixed",
    )



def normalize_optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser().resolve()



def normalize_integrations_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = default_integrations()
    for provider_name in ["radarr", "sonarr"]:
        provider = payload.get(provider_name, {})
        normalized[provider_name] = {
            "enabled": bool(provider.get("enabled")),
            "base_url": str(provider.get("base_url", "")).strip(),
            "api_key": str(provider.get("api_key", "")).strip(),
            "root_folder_path": str(provider.get("root_folder_path", "")).strip(),
        }

    options = payload.get("sync_options", {})
    normalized["sync_options"] = {
        "sync_after_apply": bool(options.get("sync_after_apply", True)),
        "rescan_after_update": bool(options.get("rescan_after_update", True)),
        "create_root_folder_if_missing": bool(options.get("create_root_folder_if_missing", True)),
    }
    return normalized



def now_iso() -> str:
    return datetime.now(UTC).isoformat()



def summarize_roots(roots: list[RootConfig]) -> list[dict[str, object]]:
    return [
        {
            "label": root.label,
            "path": str(root.path),
            "priority": root.priority,
            "kind": root.kind,
        }
        for root in roots
    ]



def summarize_apply_job(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"completed": 0, "error": 0, "skipped": 0, "applied": 0, "dry_run": 0}
    for result in results:
        status = result.get("status")
        if status == "error":
            summary["error"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "applied":
            summary["applied"] += 1
            summary["completed"] += 1
        elif status == "dry-run":
            summary["dry_run"] += 1
            summary["completed"] += 1
    return summary



def preview_actions(actions: list[dict]) -> list[dict[str, object]]:
    return [
        {
            "type": action.get("type"),
            "reason": action.get("reason"),
            "source": action.get("source"),
            "destination": action.get("destination"),
            "keep_path": action.get("keep_path"),
        }
        for action in actions[:20]
    ]



def preview_results(results: list[dict]) -> list[dict[str, object]]:
    return [
        {
            "status": result.get("status"),
            "type": result.get("type"),
            "source": result.get("source"),
            "destination": result.get("destination"),
            "keep_path": result.get("keep_path"),
            "message": result.get("message"),
            "operations": result.get("operations", [])[:8],
        }
        for result in results[:20]
    ]
