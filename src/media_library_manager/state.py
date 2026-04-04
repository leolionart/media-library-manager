from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .lan_connections import default_lan_connections, normalize_lan_connections, redact_lan_connections
from .models import LibraryTargets, RootConfig
from .sync_integrations import default_integrations


ACTIVITY_LOG_LIMIT = 200
JOB_LOG_LIMIT = 120
MANAGED_FOLDER_KEYS = ["id", "connection_id", "connection_label", "share_name", "path", "label"]


class StateStore:
    def __init__(self, state_file: str | Path):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.report_file = self.state_file.parent / "last-report.json"
        self.plan_file = self.state_file.parent / "last-plan.json"
        self.apply_file = self.state_file.parent / "last-apply.json"
        self.sync_file = self.state_file.parent / "last-sync.json"
        if not self.state_file.exists():
            self._write_state(self.default_state())

    def default_state(self) -> dict[str, Any]:
        return {
            "version": 4,
            "roots": [],
            "targets": {
                "movie_root": None,
                "series_root": None,
                "review_root": None,
            },
            "integrations": default_integrations(),
            "lan_connections": default_lan_connections(),
            "managed_folders": [],
            "last_scan_at": None,
            "last_plan_at": None,
            "last_apply_at": None,
            "last_sync_at": None,
            "activity_log": [],
            "current_job": None,
        }

    def load_state(self) -> dict[str, Any]:
        defaults = self.default_state()
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except JSONDecodeError:
            state = defaults
        merged = {**defaults, **state}
        merged["targets"] = {**defaults["targets"], **state.get("targets", {})}
        merged["integrations"] = {**defaults["integrations"], **state.get("integrations", {})}
        for provider_name in ["radarr", "sonarr"]:
            merged["integrations"][provider_name] = {
                **defaults["integrations"][provider_name],
                **state.get("integrations", {}).get(provider_name, {}),
            }
        merged["integrations"]["sync_options"] = {
            **defaults["integrations"]["sync_options"],
            **state.get("integrations", {}).get("sync_options", {}),
        }
        merged["lan_connections"] = normalize_lan_connections(state.get("lan_connections"))
        merged["managed_folders"] = self._normalize_managed_folders(state.get("managed_folders"))
        merged["activity_log"] = state.get("activity_log", [])
        merged["current_job"] = self._normalize_job(state.get("current_job"))
        return merged

    def save_roots(self, roots: list[RootConfig]) -> dict[str, Any]:
        state = self.load_state()
        state["roots"] = [root.to_dict() for root in roots]
        self._write_state(state)
        return state

    def list_roots(self) -> list[RootConfig]:
        return [
            RootConfig(
                path=Path(item["path"]),
                label=item["label"],
                priority=int(item.get("priority", 50)),
                kind=item.get("kind", "mixed"),
                connection_id=str(item.get("connection_id", "") or ""),
                connection_label=str(item.get("connection_label", "") or ""),
            )
            for item in self.load_state()["roots"]
        ]

    def add_root(self, root: RootConfig) -> dict[str, Any]:
        roots = self.list_roots()
        roots = [item for item in roots if str(item.path) != str(root.path)]
        roots.append(root)
        roots.sort(key=lambda item: (-item.priority, str(item.path)))
        return self.save_roots(roots)

    def remove_root(self, root_path: str | Path) -> dict[str, Any]:
        path = Path(root_path).expanduser().resolve()
        roots = [item for item in self.list_roots() if item.path != path]
        return self.save_roots(roots)

    def load_targets(self) -> LibraryTargets:
        data = self.load_state()["targets"]
        return LibraryTargets(
            movie_root=self._path_or_none(data.get("movie_root")),
            series_root=self._path_or_none(data.get("series_root")),
            review_root=self._path_or_none(data.get("review_root")),
        )

    def save_targets(self, targets: LibraryTargets) -> dict[str, Any]:
        state = self.load_state()
        state["targets"] = {
            "movie_root": str(targets.movie_root) if targets.movie_root else None,
            "series_root": str(targets.series_root) if targets.series_root else None,
            "review_root": str(targets.review_root) if targets.review_root else None,
        }
        self._write_state(state)
        return state

    def load_integrations(self) -> dict[str, Any]:
        return self.load_state()["integrations"]

    def save_integrations(self, integrations: dict[str, Any]) -> dict[str, Any]:
        state = self.load_state()
        state["integrations"] = integrations
        self._write_state(state)
        return state

    def load_lan_connections(self) -> dict[str, Any]:
        return normalize_lan_connections(self.load_state().get("lan_connections"))

    def save_lan_connections(self, connections: dict[str, Any]) -> dict[str, Any]:
        state = self.load_state()
        state["lan_connections"] = normalize_lan_connections(connections)
        self._write_state(state)
        return state

    def list_managed_folders(self) -> list[dict[str, Any]]:
        return list(self.load_state().get("managed_folders", []))

    def save_managed_folders(self, folders: list[dict[str, Any]]) -> dict[str, Any]:
        state = self.load_state()
        state["managed_folders"] = self._normalize_managed_folders(folders)
        self._write_state(state)
        return state

    def add_managed_folder(self, folder: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        folders = [item for item in self.list_managed_folders() if not self._same_managed_folder(item, folder)]
        normalized = self._normalize_managed_folder(folder)
        folders.append(normalized)
        folders.sort(key=lambda item: (item["connection_label"].lower(), item["path"].lower()))
        state = self.save_managed_folders(folders)
        return state, normalized

    def remove_managed_folder(self, folder_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        folders = self.list_managed_folders()
        removed = next((item for item in folders if item["id"] == folder_id), None)
        next_folders = [item for item in folders if item["id"] != folder_id]
        state = self.save_managed_folders(next_folders)
        return state, removed

    def save_report(self, report: dict[str, Any]) -> None:
        self.report_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        state = self.load_state()
        state["last_scan_at"] = report.get("generated_at")
        self._write_state(state)

    def load_report(self) -> dict[str, Any] | None:
        if not self.report_file.exists():
            return None
        return json.loads(self.report_file.read_text(encoding="utf-8"))

    def save_plan(self, plan: dict[str, Any]) -> None:
        self.plan_file.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        state = self.load_state()
        state["last_plan_at"] = plan.get("generated_at")
        self._write_state(state)

    def load_plan(self) -> dict[str, Any] | None:
        if not self.plan_file.exists():
            return None
        return json.loads(self.plan_file.read_text(encoding="utf-8"))

    def save_apply_result(self, result: dict[str, Any]) -> None:
        self.apply_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        state = self.load_state()
        state["last_apply_at"] = result.get("generated_at")
        self._write_state(state)

    def load_apply_result(self) -> dict[str, Any] | None:
        if not self.apply_file.exists():
            return None
        return json.loads(self.apply_file.read_text(encoding="utf-8"))

    def save_sync_result(self, result: dict[str, Any]) -> None:
        self.sync_file.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        state = self.load_state()
        state["last_sync_at"] = result.get("generated_at")
        self._write_state(state)

    def load_sync_result(self) -> dict[str, Any] | None:
        if not self.sync_file.exists():
            return None
        return json.loads(self.sync_file.read_text(encoding="utf-8"))

    def api_payload(self) -> dict[str, Any]:
        state = self.load_state()
        payload = {
            "version": state["version"],
            "roots": state["roots"],
            "targets": state["targets"],
            "integrations": state["integrations"],
            "lan_connections": redact_lan_connections(state["lan_connections"]),
            "managed_folders": state.get("managed_folders", []),
            "last_scan_at": state.get("last_scan_at"),
            "last_plan_at": state.get("last_plan_at"),
            "last_apply_at": state.get("last_apply_at"),
            "last_sync_at": state.get("last_sync_at"),
            "activity_log": state.get("activity_log", []),
            "current_job": state.get("current_job"),
            "report": self.load_report(),
            "plan": self.load_plan(),
            "apply_result": self.load_apply_result(),
            "sync_result": self.load_sync_result(),
        }
        return payload

    def load_current_job(self) -> dict[str, Any] | None:
        return self.load_state().get("current_job")

    def start_job(
        self,
        *,
        kind: str,
        message: str,
        summary: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now_iso()
        job = {
            "id": f"{kind}-{time.time_ns()}",
            "kind": kind,
            "status": "running",
            "message": message,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "summary": self._normalize_job_summary(summary),
            "details": details or {},
            "logs": [self._job_log_entry(level="info", message=message, details=details)],
        }
        state = self.load_state()
        state["current_job"] = job
        self._write_state(state)
        return job

    def _normalize_managed_folders(self, raw: Any) -> list[dict[str, Any]]:
        folders: list[dict[str, Any]] = []
        for item in raw or []:
            folders.append(self._normalize_managed_folder(item))
        return folders

    def _normalize_managed_folder(self, folder: dict[str, Any]) -> dict[str, Any]:
        normalized = {key: str(folder.get(key) or "").strip() for key in MANAGED_FOLDER_KEYS}
        normalized["path"] = self._normalize_share_path(normalized["path"])
        normalized["share_name"] = normalized["share_name"].strip("/")
        normalized["id"] = normalized["id"] or f"folder-{time.time_ns()}"
        normalized["label"] = normalized["label"] or Path(normalized["path"]).name or normalized["path"] or normalized["id"]
        return normalized

    def _same_managed_folder(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        normalized_right = self._normalize_managed_folder(right)
        normalized_left = self._normalize_managed_folder(left)
        return (
            normalized_left["connection_id"] == normalized_right["connection_id"]
            and normalized_left["share_name"] == normalized_right["share_name"]
            and normalized_left["path"] == normalized_right["path"]
        )

    def _normalize_share_path(self, value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return "/"
        return "/" + value.strip("/")

    def append_job_log(
        self,
        *,
        level: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        state = self.load_state()
        job = self._normalize_job(state.get("current_job"))
        if job is None:
            return None
        logs = job.get("logs", [])
        logs.append(self._job_log_entry(level=level, message=message, details=details))
        job["logs"] = logs[-JOB_LOG_LIMIT:]
        job["updated_at"] = self._now_iso()
        state["current_job"] = job
        self._write_state(state)
        return job

    def update_job_progress(self, summary: dict[str, Any]) -> dict[str, Any] | None:
        state = self.load_state()
        job = self._normalize_job(state.get("current_job"))
        if job is None:
            return None
        job["summary"] = self._normalize_job_summary({**job.get("summary", {}), **summary})
        job["updated_at"] = self._now_iso()
        state["current_job"] = job
        self._write_state(state)
        return job

    def finish_job(
        self,
        *,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        state = self.load_state()
        job = self._normalize_job(state.get("current_job"))
        if job is None:
            return None
        if summary:
            job["summary"] = self._normalize_job_summary({**job.get("summary", {}), **summary})
        if details is not None:
            job["details"] = details
        now = self._now_iso()
        job["status"] = status
        job["message"] = message
        job["updated_at"] = now
        job["finished_at"] = now
        logs = job.get("logs", [])
        logs.append(self._job_log_entry(level="error" if status == "error" else "info", message=message, details=details))
        job["logs"] = logs[-JOB_LOG_LIMIT:]
        state["current_job"] = job
        self._write_state(state)
        return job

    def append_activity(
        self,
        *,
        kind: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.load_state()
        entry = {
            "id": f"{kind}-{time.time_ns()}",
            "kind": kind,
            "status": status,
            "message": message,
            "created_at": self._now_iso(),
            "details": details or {},
        }
        history = state.get("activity_log", [])
        history.insert(0, entry)
        state["activity_log"] = history[:ACTIVITY_LOG_LIMIT]
        self._write_state(state)
        return entry

    def _write_state(self, state: dict[str, Any]) -> None:
        temp_path = self.state_file.with_suffix(f"{self.state_file.suffix}.tmp")
        temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self.state_file)

    @staticmethod
    def _path_or_none(value: str | None) -> Path | None:
        if not value:
            return None
        return Path(value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _job_log_entry(*, level: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ts": datetime.now(UTC).isoformat(),
            "level": level,
            "message": message,
            "details": details or {},
        }

    @staticmethod
    def _normalize_job_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
        base = {
            "total": 0,
            "completed": 0,
            "error": 0,
            "skipped": 0,
        }
        if not summary:
            return base
        return {**base, **summary}

    def _normalize_job(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        if not job or not isinstance(job, dict):
            return None
        details = job.get("details", {})
        if not isinstance(details, dict):
            details = {}
        logs = job.get("logs", [])
        if not isinstance(logs, list):
            logs = []
        return {
            **job,
            "summary": self._normalize_job_summary(job.get("summary")),
            "details": details,
            "logs": logs[-JOB_LOG_LIMIT:],
        }
