from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .browser import browse_path, list_mounts
from .lan_connections import (
    build_cd_command,
    browse_smb_path,
    create_smb_directory,
    delete_smb_directory,
    normalize_stored_smb_connection,
    parent_share_path,
    remove_smb_connection,
    resolve_smb_connection,
    resolve_smb_connection_for_test,
    test_smb_connection,
    upsert_smb_connection,
)
from .models import LibraryTargets, RootConfig
from .network import discover_lan_devices
from .operations import apply_plan, delete_folder, move_folder, move_folder_contents
from .operation_storage import OperationStorageRouter
from .planner import load_report, plan_actions
from .scanner import scan_roots
from .scanner_storage import StorageManagerScannerStorage
from .state import StateStore
from .storage import StoragePath as ScanStoragePath, default_storage_manager
from .sync_integrations import default_integrations, list_provider_items, refresh_provider_item, sync_after_apply, test_integrations


PLAN_PROGRESS_TOTAL = 3
SMB_SCAN_HASH_TIMEOUT = 180


class JobCancelledError(RuntimeError):
    pass


def format_root_directory_error(root: RootConfig) -> str:
    if root.storage_uri.startswith("smb://"):
        return "Selected SMB root is invalid or unavailable."
    if root.connection_id:
        return "Selected SMB folder is not mounted in the runtime or is no longer available."
    return f"path is not a directory: {root.path}"


def root_requires_local_directory(root: RootConfig) -> bool:
    return not root.storage_uri.startswith("smb://")


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
        self._run_with_api_error_boundary(self._do_get)

    def _operation_storage_router(self) -> OperationStorageRouter:
        lan_connections = self.store.load_lan_connections()
        return OperationStorageRouter(
            smb_connection_resolver=lambda connection_id: resolve_smb_connection(lan_connections, connection_id)
        )

    def _do_get(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/legacy":
            self._serve_static("legacy-index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.svg":
            self._serve_static("favicon.svg", "image/svg+xml")
            return
        if parsed.path == "/app.js":
            self._serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/legacy-app.js":
            self._serve_static("legacy-app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/legacy-styles.css":
            self._serve_static("legacy-styles.css", "text/css; charset=utf-8")
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
        if parsed.path == "/api/lan/connections":
            self._send_json(self.store.api_payload()["lan_connections"])
            return
        if parsed.path == "/api/operations/folders":
            try:
                self._send_json(build_operations_folder_inventory(self.store.list_roots(), self.store.load_lan_connections()))
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/operations/folders/children":
            params = parse_qs(parsed.query)
            storage_uri = params.get("storage_uri", [None])[0]
            root_storage_uri = params.get("root_storage_uri", [None])[0]
            if not storage_uri or not root_storage_uri:
                self._send_json(
                    {"error": "storage_uri and root_storage_uri query parameters are required"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                self._send_json(
                    build_operations_folder_children(
                        self.store.list_roots(),
                        self.store.load_lan_connections(),
                        storage_uri=storage_uri,
                        root_storage_uri=root_storage_uri,
                    )
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/operations/folders/tree":
            params = parse_qs(parsed.query)
            try:
                max_depth = int(params.get("depth", ["4"])[0])
            except ValueError:
                self._send_json({"error": "depth must be an integer"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                self._send_json(
                    build_operations_folder_tree(
                        self.store.list_roots(),
                        self.store.load_lan_connections(),
                        max_depth=max_depth,
                    )
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/smb/browse":
            params = parse_qs(parsed.query)
            connection_id = params.get("connection_id", [None])[0]
            if not connection_id:
                self._send_json({"error": "missing connection_id query parameter"}, status=HTTPStatus.BAD_REQUEST)
                return
            connection = resolve_smb_connection(self.store.load_lan_connections(), connection_id)
            if connection is None:
                self._send_json({"error": f"connection not found: {connection_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            result = browse_smb_path(
                connection,
                params.get("path", [None])[0],
                share_name=params.get("share_name", [None])[0],
                host_scope=params.get("scope", [None])[0] == "host",
            )
            if result.get("status") != "success":
                self._send_json({"error": result.get("message", "SMB browse failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return
        if parsed.path == "/api/browse":
            params = parse_qs(parsed.query)
            requested_path = params.get("path", [None])[0]
            try:
                self._send_json(browse_path(requested_path))
            except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path in {"/api/integrations/radarr/items", "/api/integrations/sonarr/items"}:
            provider = "radarr" if "radarr" in parsed.path else "sonarr"
            result = list_provider_items(self.store.load_integrations(), provider)
            if result.get("status") != "success":
                self._send_json({"error": result.get("message", "provider list failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        self._run_with_api_error_boundary(self._do_post)

    def _do_post(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/roots":
            payload = self._read_json()
            root = normalize_root_payload(payload)
            if root_requires_local_directory(root) and not root.path.is_dir():
                self._send_json({"error": format_root_directory_error(root)}, status=HTTPStatus.BAD_REQUEST)
                return
            original_path = str(payload.get("original_path") or "").strip()
            if original_path:
                self.store.update_root(original_path, root)
            else:
                self.store.add_root(root)
            self.store.append_activity(
                kind="config",
                status="success",
                message="Updated connected folder." if original_path else "Added scan root.",
                details={
                    "original_path": original_path or None,
                    "label": root.label,
                    "path": str(root.path),
                    "priority": root.priority,
                    "kind": root.kind,
                    "connection_id": root.connection_id,
                    "connection_label": root.connection_label,
                },
            )
            self._send_json(self.store.api_payload(), status=HTTPStatus.OK if original_path else HTTPStatus.CREATED)
            return

        if parsed.path == "/api/roots/bulk":
            payload = self._read_json()
            roots = [normalize_root_payload(item) for item in payload.get("roots", [])]
            if not roots:
                self._send_json({"error": "at least one root is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            invalid_root = next((root for root in roots if root_requires_local_directory(root) and not root.path.is_dir()), None)
            if invalid_root:
                self._send_json({"error": format_root_directory_error(invalid_root)}, status=HTTPStatus.BAD_REQUEST)
                return
            for root in roots:
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
                        "connection_id": root.connection_id,
                        "connection_label": root.connection_label,
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

        if parsed.path == "/api/lan/connections":
            payload = self._read_json()
            connections, saved = upsert_smb_connection(self.store.load_lan_connections(), payload)
            self.store.save_lan_connections(connections)
            self.store.append_activity(
                kind="lan",
                status="success",
                message="Saved SMB connection profile.",
                details={
                    "id": saved["id"],
                    "label": saved["label"],
                    "host": saved["host"],
                    "share_name": saved["share_name"],
                    "base_path": saved["base_path"],
                    "enabled": saved["enabled"],
                },
            )
            self._send_json(self.store.api_payload()["lan_connections"], status=HTTPStatus.CREATED)
            return

        if parsed.path == "/api/lan/connections/test":
            payload = self._read_json()
            connection = resolve_smb_connection_for_test(self.store.load_lan_connections(), payload)
            result = test_smb_connection(connection)
            activity_status = "success" if result.get("status") == "success" else "error"
            self.store.append_activity(
                kind="lan",
                status=activity_status,
                message="SMB connection test finished.",
                details={
                    "id": connection["id"],
                    "label": connection["label"],
                    "host": connection["host"],
                    "share_name": connection["share_name"],
                    "result": result,
                },
            )
            self._send_json(result, status=HTTPStatus.OK if result.get("status") == "success" else HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/managed-folders":
            payload = self._read_json()
            connection_id = str(payload.get("connection_id") or "").strip()
            path = str(payload.get("path") or "").strip()
            connection = resolve_smb_connection(self.store.load_lan_connections(), connection_id)
            if connection is None:
                self._send_json({"error": f"connection not found: {connection_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            state, saved = self.store.add_managed_folder(
                {
                    "connection_id": connection["id"],
                    "connection_label": connection["label"],
                    "share_name": connection["share_name"],
                    "path": path,
                    "label": payload.get("label") or Path(path or "/").name or connection["share_name"],
                }
            )
            self.store.append_activity(
                kind="folder",
                status="success",
                message="Added managed SMB folder.",
                details={"id": saved["id"], "connection_id": saved["connection_id"], "path": saved["path"]},
            )
            self._send_json({"managed_folders": state["managed_folders"]}, status=HTTPStatus.CREATED)
            return

        if parsed.path == "/api/smb/folders":
            payload = self._read_json()
            connection_id = str(payload.get("connection_id") or "").strip()
            connection = resolve_smb_connection(self.store.load_lan_connections(), connection_id)
            if connection is None:
                self._send_json({"error": f"connection not found: {connection_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            result = create_smb_directory(connection, payload.get("parent_path"), str(payload.get("folder_name") or ""))
            if result.get("status") != "success":
                self.store.append_activity(
                    kind="folder",
                    status="error",
                    message="SMB folder creation failed.",
                    details={"connection_id": connection_id, "parent_path": payload.get("parent_path"), "error": result.get("message")},
                )
                self._send_json({"error": result.get("message", "SMB folder creation failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self.store.append_activity(
                kind="folder",
                status="success",
                message="Created SMB folder.",
                details={"connection_id": connection_id, "path": result["path"]},
            )
            self._send_json(result, status=HTTPStatus.CREATED)
            return

        if parsed.path == "/api/folders/move":
            payload = self._read_json()
            result = move_folder(
                str(payload.get("source") or ""),
                str(payload.get("destination_parent") or ""),
                execute=bool(payload.get("execute")),
                storage_router=self._operation_storage_router(),
            )
            if result.get("status") == "error":
                self.store.append_activity(
                    kind="folder",
                    status="error",
                    message="Folder move failed.",
                    details={
                        "source": payload.get("source"),
                        "destination_parent": payload.get("destination_parent"),
                        "error": result.get("message"),
                    },
                )
                self._send_json({"error": result.get("message", "folder move failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self.store.append_activity(
                kind="folder",
                status="success" if result.get("status") == "applied" else "running",
                message="Folder move preview created." if result.get("status") == "dry-run" else "Folder moved.",
                details=result,
            )
            self._send_json(result)
            return

        if parsed.path == "/api/folders/move-to-provider":
            payload = self._read_json()
            provider = str(payload.get("provider") or "").strip()
            item_id = int(payload.get("item_id") or 0)
            destination = str(payload.get("destination") or "").strip()
            result = move_folder_contents(
                str(payload.get("source") or ""),
                destination,
                execute=bool(payload.get("execute")),
                storage_router=self._operation_storage_router(),
            )
            if result.get("status") == "error":
                self.store.append_activity(
                    kind="folder",
                    status="error",
                    message="Provider folder move failed.",
                    details={"provider": provider, "source": payload.get("source"), "destination": destination, "error": result.get("message")},
                )
                self._send_json({"error": result.get("message", "provider folder move failed")}, status=HTTPStatus.BAD_REQUEST)
                return

            refresh_result = None
            if result.get("status") == "applied":
                refresh_result = refresh_provider_item(self.store.load_integrations(), provider, item_id)
                if refresh_result.get("status") != "success":
                    self.store.append_activity(
                        kind="integration",
                        status="error",
                        message=f"{provider.capitalize()} refresh after folder move failed.",
                        details=refresh_result,
                    )
                    self._send_json(
                        {
                            "error": refresh_result.get("message", "provider refresh failed"),
                            "move_result": result,
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

            message = "Provider folder move preview created." if result.get("status") == "dry-run" else "Folder moved into provider path."
            self.store.append_activity(
                kind="folder",
                status="success" if result.get("status") == "applied" else "running",
                message=message,
                details={"provider": provider, "item_id": item_id, "destination": destination, "move_result": result, "refresh_result": refresh_result},
            )
            self._send_json({"move_result": result, "refresh_result": refresh_result})
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

        if parsed.path == "/api/process/cancel":
            job = self.store.request_job_cancel()
            if job is None:
                self._send_json({"error": "no running job to cancel"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"current_job": job})
            return

        if parsed.path == "/api/scan":
            payload = self._read_json()
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

            scan_roots_selection = build_selected_scan_roots(payload.get("folders", []), roots=roots)
            if not scan_roots_selection:
                self.store.append_activity(
                    kind="scan",
                    status="error",
                    message="Duplicate detection needs at least one selected folder.",
                    details={"error": "no folders selected"},
                )
                self._send_json({"error": "select at least one folder to scan"}, status=HTTPStatus.BAD_REQUEST)
                return

            roots_summary = summarize_roots(scan_roots_selection)
            job_details = {
                "root_count": len(scan_roots_selection),
                "roots": roots_summary,
                "source_root_count": len(roots),
            }
            self.store.start_job(
                kind="scan",
                message="Started duplicate detection for selected folders.",
                summary={"total": len(scan_roots_selection), "completed": 0},
                details=job_details,
            )
            self.store.append_activity(
                kind="scan",
                status="running",
                message="Started duplicate detection for selected folders.",
                details=job_details,
            )

            lan_connections = self.store.load_lan_connections()
            scan_backend = build_scan_storage_backend(roots=scan_roots_selection, lan_connections=lan_connections)
            if scan_backend is not None:
                smb_root_count = sum(1 for root in scan_roots_selection if (root.storage_uri or "").startswith("smb://"))
                self.store.append_job_log(
                    level="info",
                    message="Using storage abstraction for scan roots.",
                    details={"smb_roots": smb_root_count, "total_roots": len(scan_roots_selection)},
                )

            try:
                report = scan_roots(
                    scan_roots_selection,
                    progress_callback=self._scan_progress_callback,
                    storage_backend=scan_backend,
                    should_cancel=self.store.is_current_job_cancel_requested,
                ).to_dict()
            except JobCancelledError:
                cancel_details = {**job_details, "cancel_requested": True}
                self.store.finish_job(status="cancelled", message="Duplicate detection cancelled.", details=cancel_details)
                self.store.append_activity(
                    kind="scan",
                    status="cancelled",
                    message="Duplicate detection cancelled.",
                    details=cancel_details,
                )
                self._send_json({"error": "scan cancelled", "cancelled": True}, status=HTTPStatus.CONFLICT)
                return
            except Exception as exc:
                error_details = {"error": str(exc), **job_details}
                self.store.finish_job(status="error", message="Duplicate detection failed.", details=error_details)
                self.store.append_activity(
                    kind="scan",
                    status="error",
                    message="Duplicate detection failed.",
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
                message="Duplicate detection completed.",
                details=success_details,
                summary={
                    "total": len(scan_roots_selection),
                    "completed": len(scan_roots_selection),
                    "indexed_files": report.get("summary", {}).get("files", 0),
                },
            )
            self.store.append_activity(
                kind="scan",
                status="success",
                message="Duplicate detection completed.",
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
                self._raise_if_cancel_requested()
                report = load_report(self.store.report_file)
                self.store.append_job_log(level="info", message="Building action plan from report.")
                self._raise_if_cancel_requested()
                plan = plan_actions(
                    report,
                    self.store.load_targets(),
                    delete_lower_quality=delete_lower_quality,
                )
                self.store.update_job_progress({"total": PLAN_PROGRESS_TOTAL, "completed": 2})
                self._raise_if_cancel_requested()
            except JobCancelledError:
                cancel_details = {**job_details, "cancel_requested": True}
                self.store.finish_job(status="cancelled", message="Action plan build cancelled.", details=cancel_details)
                self.store.append_activity(
                    kind="plan",
                    status="cancelled",
                    message="Action plan build cancelled.",
                    details=cancel_details,
                )
                self._send_json({"error": "plan cancelled", "cancelled": True}, status=HTTPStatus.CONFLICT)
                return
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
                    should_cancel=self.store.is_current_job_cancel_requested,
                )
                if result.get("status") == "cancelled" or self.store.is_current_job_cancel_requested():
                    raise JobCancelledError()
            except JobCancelledError:
                cancel_details = {**job_details, "cancel_requested": True}
                self.store.finish_job(
                    status="cancelled",
                    message=f"{'Execute' if execute else 'Dry-run'} apply cancelled.",
                    details=cancel_details,
                )
                self.store.append_activity(
                    kind="apply",
                    status="cancelled",
                    message=f"{'Execute' if execute else 'Dry-run'} apply cancelled.",
                    details=cancel_details,
                )
                self._send_json({"error": "apply cancelled", "cancelled": True}, status=HTTPStatus.CONFLICT)
                return
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
        self._run_with_api_error_boundary(self._do_delete)

    def _do_delete(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/folders":
            params = parse_qs(parsed.query)
            path_value = params.get("path", [None])[0]
            execute = params.get("execute", ["false"])[0].lower() == "true"
            if not path_value:
                self._send_json({"error": "missing path query parameter"}, status=HTTPStatus.BAD_REQUEST)
                return
            result = delete_folder(path_value, execute=execute, storage_router=self._operation_storage_router())
            if result.get("status") == "error":
                self.store.append_activity(
                    kind="folder",
                    status="error",
                    message="Folder delete failed.",
                    details={"path": path_value, "error": result.get("message")},
                )
                self._send_json({"error": result.get("message", "folder delete failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self.store.append_activity(
                kind="folder",
                status="success" if result.get("status") == "applied" else "running",
                message="Folder delete preview created." if result.get("status") == "dry-run" else "Folder deleted.",
                details=result,
            )
            self._send_json(result)
            return
        if parsed.path == "/api/managed-folders":
            params = parse_qs(parsed.query)
            folder_id = params.get("id", [None])[0]
            if not folder_id:
                self._send_json({"error": "missing id query parameter"}, status=HTTPStatus.BAD_REQUEST)
                return
            state, removed = self.store.remove_managed_folder(folder_id)
            if removed is None:
                self._send_json({"error": f"managed folder not found: {folder_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            self.store.append_activity(
                kind="folder",
                status="success",
                message="Removed managed SMB folder.",
                details={"id": removed["id"], "path": removed["path"], "connection_id": removed["connection_id"]},
            )
            self._send_json({"managed_folders": state["managed_folders"]})
            return
        if parsed.path == "/api/smb/folders":
            params = parse_qs(parsed.query)
            connection_id = params.get("connection_id", [None])[0]
            path_value = params.get("path", [None])[0]
            if not connection_id or not path_value:
                self._send_json({"error": "missing connection_id or path query parameter"}, status=HTTPStatus.BAD_REQUEST)
                return
            connection = resolve_smb_connection(self.store.load_lan_connections(), connection_id)
            if connection is None:
                self._send_json({"error": f"connection not found: {connection_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            result = delete_smb_directory(connection, path_value)
            if result.get("status") != "success":
                self.store.append_activity(
                    kind="folder",
                    status="error",
                    message="SMB folder deletion failed.",
                    details={"connection_id": connection_id, "path": path_value, "error": result.get("message")},
                )
                self._send_json({"error": result.get("message", "SMB folder deletion failed")}, status=HTTPStatus.BAD_REQUEST)
                return
            self.store.append_activity(
                kind="folder",
                status="success",
                message="Deleted SMB folder.",
                details={"connection_id": connection_id, "path": path_value},
            )
            self._send_json(result)
            return
        if parsed.path == "/api/lan/connections":
            params = parse_qs(parsed.query)
            connection_id = params.get("id", [None])[0]
            if not connection_id:
                self._send_json({"error": "missing id query parameter"}, status=HTTPStatus.BAD_REQUEST)
                return
            connections, removed = remove_smb_connection(self.store.load_lan_connections(), connection_id)
            if removed is None:
                self._send_json({"error": f"connection not found: {connection_id}"}, status=HTTPStatus.NOT_FOUND)
                return
            self.store.save_lan_connections(connections)
            self.store.append_activity(
                kind="lan",
                status="success",
                message="Removed SMB connection profile.",
                details={"id": removed["id"], "label": removed["label"], "host": removed["host"]},
            )
            self._send_json(self.store.api_payload()["lan_connections"])
            return
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

    def _run_with_api_error_boundary(self, handler: Any) -> None:
        try:
            handler()
        except Exception as exc:
            if self.path.startswith("/api/"):
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            raise

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        if self.path.startswith("/api/"):
            try:
                status = HTTPStatus(code)
                default_message = message or status.phrase
                self._send_json({"error": default_message}, status=status)
                return
            except ValueError:
                self._send_json({"error": message or "Request failed"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        super().send_error(code, message, explain)

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
        self._raise_if_cancel_requested()
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
        self._raise_if_cancel_requested()
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

    def _raise_if_cancel_requested(self) -> None:
        if self.store.is_current_job_cancel_requested():
            raise JobCancelledError()



def normalize_root_payload(payload: dict) -> RootConfig:
    storage_uri = str(payload.get("storage_uri") or "").strip()
    raw_path = str(payload.get("path") or "").strip()
    path = build_root_path(storage_uri=storage_uri, raw_path=raw_path)
    return RootConfig(
        path=path,
        label=(payload.get("label") or path.name).strip(),
        priority=int(payload.get("priority", 50)),
        kind=(payload.get("kind") or "mixed").strip() or "mixed",
        connection_id=str(payload.get("connection_id") or "").strip(),
        connection_label=str(payload.get("connection_label") or "").strip(),
        storage_uri=storage_uri,
        share_name=str(payload.get("share_name") or "").strip().strip("/"),
    )


def build_root_path(*, storage_uri: str, raw_path: str) -> Path:
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    if storage_uri.startswith("local://"):
        return Path(unquote(urlparse(storage_uri).path or "/")).expanduser().resolve()
    if storage_uri.startswith("smb://"):
        parsed = urlparse(storage_uri)
        params = parse_qs(parsed.query)
        connection_id = sanitize_path_segment(unquote(params.get("connection_id", [""])[0]), "connection")
        share_name = sanitize_path_segment(unquote(parsed.netloc), "share")
        share_path = "/" + str(parsed.path or "").strip("/")
        base = Path("/") / "smb" / connection_id / share_name
        if share_path in {"", "/"}:
            return base
        decoded_segments = [sanitize_path_segment(unquote(segment), "folder") for segment in share_path.strip("/").split("/") if segment]
        return base.joinpath(*decoded_segments)
    return Path("/").resolve()


def sanitize_path_segment(value: str, fallback: str) -> str:
    clean = str(value or "").strip().replace("/", "_")
    return clean or fallback



def normalize_optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser().resolve()


def build_selected_scan_roots(folder_payloads: list[dict[str, Any]], *, roots: list[RootConfig]) -> list[RootConfig]:
    selected_roots: list[RootConfig] = []
    seen: set[tuple[str, str]] = set()

    for folder in folder_payloads:
        storage_uri = str(folder.get("storage_uri") or "").strip()
        path_value = str(folder.get("path") or "").strip()
        root_path_value = str(folder.get("root_path") or "").strip()
        root_storage_uri_value = str(folder.get("root_storage_uri") or "").strip()

        matching_root = next(
            (
                root
                for root in roots
                if (
                    (
                        root_storage_uri_value
                        and root.storage_uri
                        and root.storage_uri == root_storage_uri_value
                    )
                    or (not root_storage_uri_value and root_path_value and str(root.path) == root_path_value)
                )
            ),
            None,
        )
        if matching_root is None:
            continue

        effective_storage_uri = storage_uri or (path_value if path_value.startswith(("local://", "smb://")) else "")
        effective_path = path_value if path_value and not path_value.startswith(("local://", "smb://")) else ""
        resolved_path = build_root_path(storage_uri=effective_storage_uri, raw_path=effective_path)
        dedupe_key = (effective_storage_uri or str(resolved_path), str(matching_root.path))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        selected_roots.append(
            RootConfig(
                path=resolved_path,
                label=str(folder.get("label") or resolved_path.name).strip() or resolved_path.name,
                priority=int(folder.get("priority", matching_root.priority)),
                kind=str(folder.get("kind") or matching_root.kind or "mixed").strip() or "mixed",
                connection_id=str(folder.get("connection_id") or matching_root.connection_id or "").strip(),
                connection_label=str(folder.get("connection_label") or matching_root.connection_label or "").strip(),
                storage_uri=effective_storage_uri,
                share_name=matching_root.share_name,
            )
        )

    return selected_roots



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
            "connection_id": root.connection_id,
            "connection_label": root.connection_label,
            "storage_uri": root.storage_uri,
            "share_name": root.share_name,
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



def build_scan_storage_backend(
    *,
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
) -> StorageManagerScannerStorage | None:
    if not any(bool(root.storage_uri) for root in roots):
        return None
    manager = default_storage_manager(lan_connections=lan_connections)
    return StorageManagerScannerStorage(
        manager,
        smb_sha256=lambda path: compute_smb_storage_sha256(path, lan_connections=lan_connections),
    )


def build_operations_folder_inventory(roots: list[RootConfig], lan_connections: dict[str, Any]) -> dict[str, Any]:
    manager = default_storage_manager(lan_connections=lan_connections)
    items: list[dict[str, Any]] = []

    for root in roots:
        root_storage_path = root_to_scan_storage_path(root)
        try:
            entries = manager.list_dir(root_storage_path)
        except Exception:
            continue
        for entry in entries:
            item_path = entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path()
            try:
                relative_path = entry.path.relative_to(root_storage_path)
            except Exception:
                relative_path = entry.name
            items.append(
                {
                    "label": entry.name,
                    "path": item_path,
                    "display_path": relative_path,
                    "root_path": str(root.path),
                    "root_label": root.label,
                    "connection_id": root.connection_id,
                    "connection_label": root.connection_label,
                    "kind": root.kind,
                    "priority": root.priority,
                    "storage_uri": entry.path.to_uri(),
                    "root_storage_uri": root.storage_uri or str(root.path),
                    "entry_type": entry.entry_type,
                    "is_file": entry.is_file,
                    "has_children": _storage_path_has_dir_children(manager, entry.path) if entry.is_dir else False,
                    "size": entry.size,
                    "modified_at": entry.modified_at,
                }
            )

    items.sort(key=lambda item: (item["label"].lower(), item["display_path"].lower()))
    return {"items": items, "summary": {"items": len(items), "roots": len(roots)}}


def build_operations_folder_children(
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    *,
    storage_uri: str,
    root_storage_uri: str,
) -> dict[str, Any]:
    root = next((candidate for candidate in roots if (candidate.storage_uri or str(candidate.path)) == root_storage_uri), None)
    if root is None:
        raise ValueError(f"unknown root: {root_storage_uri}")

    manager = default_storage_manager(lan_connections=lan_connections)
    root_storage_path = root_to_scan_storage_path(root)
    current_path = ScanStoragePath.from_uri(storage_uri)

    try:
        entries = manager.list_dir(current_path)
    except Exception:
        entries = []

    items: list[dict[str, Any]] = []
    for entry in entries:
        try:
            relative_path = entry.path.relative_to(root_storage_path)
        except Exception:
            relative_path = entry.name
        items.append(
            {
                "label": entry.name,
                "key": entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path(),
                "path": entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path(),
                "display_path": relative_path,
                "root_path": str(root.path),
                "root_label": root.label,
                "connection_id": root.connection_id,
                "connection_label": root.connection_label,
                "kind": root.kind,
                "priority": root.priority,
                "storage_uri": entry.path.to_uri(),
                "root_storage_uri": root.storage_uri or str(root.path),
                "is_root": False,
                "entry_type": entry.entry_type,
                "is_file": entry.is_file,
                "has_children": _storage_path_has_dir_children(manager, entry.path) if entry.is_dir else False,
                "size": entry.size,
                "modified_at": entry.modified_at,
            }
        )

    items.sort(key=lambda item: (item["label"].lower(), item["display_path"].lower()))
    return {"items": items}


def build_operations_folder_tree(
    roots: list[RootConfig],
    lan_connections: dict[str, Any],
    *,
    max_depth: int = 4,
) -> dict[str, Any]:
    bounded_depth = max(1, min(max_depth, 12))
    manager = default_storage_manager(lan_connections=lan_connections)
    tree: list[dict[str, Any]] = []
    total_nodes = 0

    for root in roots:
        root_storage_path = root_to_scan_storage_path(root)
        children = _build_storage_tree_nodes(
            manager,
            root_storage_path,
            root_storage_path,
            current_depth=1,
            max_depth=bounded_depth,
        )
        total_nodes += _count_tree_nodes(children)
        tree.append(
            {
                "label": root.label,
                "key": root.storage_uri or str(root.path),
                "path": str(root.path),
                "display_path": root.label,
                "storage_uri": root.storage_uri or root_storage_path.to_uri(),
                "root_path": str(root.path),
                "root_label": root.label,
                "connection_id": root.connection_id,
                "connection_label": root.connection_label,
                "kind": root.kind,
                "priority": root.priority,
                "share_name": root.share_name,
                "depth": 0,
                "is_root": True,
                "has_children": bool(children),
                "children": children,
            }
        )

    tree.sort(key=lambda item: (item["label"].lower(), item["root_label"].lower()))
    return {
        "items": tree,
        "summary": {
            "roots": len(roots),
            "nodes": total_nodes,
            "max_depth": bounded_depth,
        },
    }


def _build_storage_tree_nodes(
    manager: Any,
    base_path: ScanStoragePath,
    current_path: ScanStoragePath,
    *,
    current_depth: int,
    max_depth: int,
) -> list[dict[str, Any]]:
    try:
        entries = manager.list_dir(current_path)
    except Exception:
        return []

    nodes: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.is_dir:
            continue
        try:
            relative_path = entry.path.relative_to(base_path)
        except Exception:
            relative_path = entry.name
        children = (
            _build_storage_tree_nodes(
                manager,
                base_path,
                entry.path,
                current_depth=current_depth + 1,
                max_depth=max_depth,
            )
            if current_depth < max_depth
            else []
        )
        nodes.append(
            {
                "label": entry.name,
                "key": entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path(),
                "path": entry.path.to_uri() if entry.path.backend == "smb" else entry.path.normalized_path(),
                "display_path": relative_path,
                "storage_uri": entry.path.to_uri(),
                "depth": current_depth,
                "has_children": bool(children),
                "children": children,
            }
        )

    nodes.sort(key=lambda item: (item["label"].lower(), item["display_path"].lower()))
    return nodes


def _count_tree_nodes(nodes: list[dict[str, Any]]) -> int:
    return sum(1 + _count_tree_nodes(node.get("children", [])) for node in nodes)


def _storage_path_has_dir_children(manager: Any, path: ScanStoragePath) -> bool:
    try:
        return any(entry.is_dir for entry in manager.list_dir(path))
    except Exception:
        return False


def root_to_scan_storage_path(root: RootConfig) -> ScanStoragePath:
    raw = root.storage_uri or str(root.path)
    if raw.startswith(("local://", "smb://")):
        return ScanStoragePath.from_uri(raw)
    return ScanStoragePath.local(raw)


def compute_smb_storage_sha256(
    path: ScanStoragePath,
    *,
    lan_connections: dict[str, Any],
    timeout: int = SMB_SCAN_HASH_TIMEOUT,
) -> str:
    if path.backend != "smb":
        raise ValueError("SMB hash callback requires an smb storage path")

    connection = resolve_smb_connection(lan_connections, path.connection_id)
    if connection is None:
        raise RuntimeError(f"SMB connection not found for scan: {path.connection_id}")

    normalized_connection = normalize_stored_smb_connection({**connection, "share_name": path.share_name})
    normalized_path = path.normalized_path()
    if normalized_path in {"", "/"}:
        raise RuntimeError("SMB hash callback requires a file path, not share root")

    parent_path = parent_share_path(normalized_path) or "/"
    file_name = PurePosixPath(normalized_path).name
    escaped_file_name = file_name.replace('"', '\\"')
    smb_command = f'{build_cd_command(parent_path)}get "{escaped_file_name}" -'

    auth_file = None
    process = None
    stderr_raw = b""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            auth_file = Path(handle.name)
            handle.write(f"username = {normalized_connection['username']}\n")
            handle.write(f"password = {normalized_connection['password']}\n")
            if normalized_connection["domain"]:
                handle.write(f"domain = {normalized_connection['domain']}\n")

        target = f"//{normalized_connection['host']}/{normalized_connection['share_name']}"
        process = subprocess.Popen(
            [
                "smbclient",
                target,
                "-A",
                str(auth_file),
                "-m",
                f"SMB{normalized_connection['version']}",
                "-c",
                smb_command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        digest = hashlib.sha256()
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

        if process.stderr is not None:
            stderr_raw = process.stderr.read() or b""
        return_code = process.wait(timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError("smbclient is not installed in the runtime") from exc
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            process.kill()
        raise RuntimeError("SMB hash operation timed out") from exc
    finally:
        if auth_file and auth_file.exists():
            auth_file.unlink(missing_ok=True)

    if return_code != 0:
        message = stderr_raw.decode("utf-8", errors="replace").strip() or "SMB hash operation failed"
        raise RuntimeError(message)

    return digest.hexdigest()


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
