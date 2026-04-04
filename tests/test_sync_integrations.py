import unittest
from unittest.mock import patch

from media_library_manager.sync_integrations import default_integrations, list_provider_items, normalize_base_url, refresh_provider_item, sync_after_apply


class FakeRadarrClient:
    def __init__(self, config):
        self.config = config
        self.updated_movies = []

    def ensure_root_folder(self, path):
        return {"path": path}

    def list_movies(self):
        return [{"id": 1, "title": "Dune Part Two", "year": 2024, "path": "/old/movies/Dune Part Two (2024)"}]

    def update_movie(self, movie):
        self.updated_movies.append(movie)
        return movie

    def refresh_movie(self, movie_id):
        return {"id": 99, "movieIds": [movie_id]}


class FakeSonarrClient:
    def __init__(self, config):
        self.config = config
        self.updated_series = []

    def ensure_root_folder(self, path):
        return {"path": path}

    def list_series(self):
        return [{"id": 2, "title": "Severance", "path": "/old/series/Severance"}]

    def update_series(self, series):
        self.updated_series.append(series)
        return series

    def refresh_series(self, series_id):
        return {"id": 100, "seriesIds": [series_id]}


class SyncIntegrationTests(unittest.TestCase):
    def test_normalize_base_url_accepts_api_root(self) -> None:
        self.assertEqual(normalize_base_url("http://radarr.local:7878/api/v3"), "http://radarr.local:7878")

    @patch("media_library_manager.sync_integrations.RadarrClient", FakeRadarrClient)
    @patch("media_library_manager.sync_integrations.SonarrClient", FakeSonarrClient)
    def test_sync_after_apply_updates_radarr_and_sonarr(self) -> None:
        integrations = default_integrations()
        integrations["radarr"].update(
            {"enabled": True, "base_url": "http://radarr.local:7878", "api_key": "abc", "root_folder_path": "/library/movies"}
        )
        integrations["sonarr"].update(
            {"enabled": True, "base_url": "http://sonarr.local:8989", "api_key": "xyz", "root_folder_path": "/library/series"}
        )

        plan = {
            "actions": [
                {
                    "type": "move",
                    "media_key": "movie:dune-part-two:2024",
                    "source": "/old/movies/Dune Part Two (2024)/Dune Part Two (2024).mkv",
                    "destination": "/library/movies/Dune Part Two (2024)/Dune Part Two (2024).mkv",
                    "details": {"title": "Dune Part Two", "year": 2024, "target_root": "/library/movies"},
                },
                {
                    "type": "move",
                    "media_key": "episode:severance:s02e03",
                    "source": "/old/series/Severance/Season 02/Severance - S02E03.mkv",
                    "destination": "/library/series/Severance/Season 02/Severance - S02E03.mkv",
                    "details": {"title": "Severance", "target_root": "/library/series"},
                },
            ]
        }
        apply_result = {
            "results": [
                {"status": "applied", "type": "move", "source": "/old/movies/Dune Part Two (2024)/Dune Part Two (2024).mkv"},
                {"status": "applied", "type": "move", "source": "/old/series/Severance/Season 02/Severance - S02E03.mkv"},
            ]
        }

        result = sync_after_apply(plan=plan, apply_result=apply_result, integrations=integrations)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["updated"], 2)

    @patch("media_library_manager.sync_integrations.RadarrClient", FakeRadarrClient)
    def test_list_provider_items_returns_radarr_items(self) -> None:
        integrations = default_integrations()
        integrations["radarr"].update({"enabled": True, "base_url": "http://radarr.local:7878", "api_key": "abc"})
        result = list_provider_items(integrations, "radarr")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["items"][0]["title"], "Dune Part Two")

    @patch("media_library_manager.sync_integrations.RadarrClient", FakeRadarrClient)
    def test_refresh_provider_item_calls_provider_refresh(self) -> None:
        integrations = default_integrations()
        integrations["radarr"].update({"enabled": True, "base_url": "http://radarr.local:7878", "api_key": "abc"})
        result = refresh_provider_item(integrations, "radarr", 1)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["item_id"], 1)
