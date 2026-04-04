from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import JsonApiClient, ProviderError


class RadarrClient(JsonApiClient):
    def test_connection(self) -> dict[str, Any]:
        status = self.get("/api/v3/system/status")
        return {
            "app": "radarr",
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

    def list_movies(self) -> list[dict[str, Any]]:
        payload = self.get("/api/v3/movie")
        if not isinstance(payload, list):
            raise ProviderError("Unexpected Radarr movie payload.")
        return payload

    def update_movie(self, movie: dict[str, Any]) -> dict[str, Any]:
        return self.put(f"/api/v3/movie/{movie['id']}?moveFiles=false", movie)

    def refresh_movie(self, movie_id: int) -> dict[str, Any]:
        return self.post("/api/v3/command", {"name": "RefreshMovie", "movieIds": [movie_id]})

    def delete_movie(self, movie_id: int, *, delete_files: bool = False, add_import_exclusion: bool = False) -> dict[str, Any]:
        return self.delete(
            f"/api/v3/movie/{movie_id}",
            query={
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": str(add_import_exclusion).lower(),
            },
        )
