from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import JsonApiClient, ProviderError


class SonarrClient(JsonApiClient):
    def test_connection(self) -> dict[str, Any]:
        status = self.get("/api/v3/system/status")
        return {
            "app": "sonarr",
            "status": "ok",
            "version": status.get("version"),
            "instance_name": status.get("instanceName"),
        }

    def ensure_root_folder(self, path: str) -> dict[str, Any] | None:
        if not path:
            return None
        normalized = str(Path(path))
        for root in self.get("/api/v3/rootfolder"):
            if str(Path(root.get("path", ""))) == normalized:
                return root
        return self.post("/api/v3/rootfolder", {"path": normalized})

    def list_series(self) -> list[dict[str, Any]]:
        payload = self.get("/api/v3/series")
        if not isinstance(payload, list):
            raise ProviderError("Unexpected Sonarr series payload.")
        return payload

    def get_series(self, series_id: int) -> dict[str, Any]:
        payload = self.get(f"/api/v3/series/{series_id}")
        if not isinstance(payload, dict):
            raise ProviderError("Unexpected Sonarr series payload.")
        return payload

    def update_series(self, series: dict[str, Any]) -> dict[str, Any]:
        return self.put(f"/api/v3/series/{series['id']}?moveFiles=false", series)

    def refresh_series(self, series_id: int) -> dict[str, Any]:
        try:
            return self.post("/api/v3/command", {"name": "RefreshSeries", "seriesId": series_id})
        except ProviderError:
            return self.post("/api/v3/command", {"name": "RefreshSeries", "seriesIds": [series_id]})

    def delete_series(self, series_id: int, *, delete_files: bool = False, add_import_exclusion: bool = False) -> dict[str, Any]:
        return self.delete(
            f"/api/v3/series/{series_id}",
            query={
                "deleteFiles": "true" if delete_files else "false",
                "addImportExclusion": "true" if add_import_exclusion else "false",
            },
        )
