from __future__ import annotations

from pathlib import Path
from typing import Any

from .providers.base import ProviderConfig, ProviderError
from .providers.radarr import RadarrClient
from .providers.sonarr import SonarrClient


def default_integrations() -> dict[str, Any]:
    return {
        "radarr": {
            "enabled": False,
            "base_url": "",
            "api_key": "",
            "root_folder_path": "",
        },
        "sonarr": {
            "enabled": False,
            "base_url": "",
            "api_key": "",
            "root_folder_path": "",
        },
        "sync_options": {
            "sync_after_apply": True,
            "rescan_after_update": True,
            "create_root_folder_if_missing": True,
        },
    }


def build_provider_config(raw: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        enabled=bool(raw.get("enabled")),
        base_url=normalize_base_url(str(raw.get("base_url", "")).strip()),
        api_key=str(raw.get("api_key", "")).strip(),
        root_folder_path=str(raw.get("root_folder_path", "")).strip(),
    )


def test_integrations(integrations: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {"radarr": {"status": "disabled"}, "sonarr": {"status": "disabled"}}
    for provider_name, client_cls in [("radarr", RadarrClient), ("sonarr", SonarrClient)]:
        config = build_provider_config(integrations.get(provider_name, {}))
        if not config.enabled:
            continue
        try:
            results[provider_name] = client_cls(config).test_connection()
        except ProviderError as exc:
            results[provider_name] = {"status": "error", "error": str(exc)}
    return results


def list_provider_items(integrations: dict[str, Any], provider: str) -> dict[str, Any]:
    if provider not in {"radarr", "sonarr"}:
        return {"status": "error", "message": f"unsupported provider: {provider}"}

    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}

    try:
        if provider == "radarr":
            client = RadarrClient(config)
            items = [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "year": item.get("year"),
                    "path": item.get("path"),
                    "hasFile": item.get("hasFile"),
                }
                for item in client.list_movies()
            ]
        else:
            client = SonarrClient(config)
            items = [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "year": item.get("year"),
                    "path": item.get("path"),
                    "statistics": item.get("statistics"),
                }
                for item in client.list_series()
            ]
    except ProviderError as exc:
        return {"status": "error", "message": str(exc)}

    items.sort(key=lambda item: ((item.get("title") or "").lower(), str(item.get("year") or "")))
    return {"status": "success", "provider": provider, "items": items}


def refresh_provider_item(integrations: dict[str, Any], provider: str, item_id: int) -> dict[str, Any]:
    config = build_provider_config(integrations.get(provider, {}))
    if not config.enabled:
        return {"status": "error", "message": f"{provider} is disabled"}
    try:
        if provider == "radarr":
            refresh = RadarrClient(config).refresh_movie(item_id)
        elif provider == "sonarr":
            refresh = SonarrClient(config).refresh_series(item_id)
        else:
            return {"status": "error", "message": f"unsupported provider: {provider}"}
    except ProviderError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "success", "provider": provider, "item_id": item_id, "refresh": refresh}


def sync_after_apply(*, plan: dict[str, Any], apply_result: dict[str, Any], integrations: dict[str, Any]) -> dict[str, Any]:
    options = integrations.get("sync_options", {})
    if not options.get("sync_after_apply", True):
        return {"status": "skipped", "reason": "sync_after_apply_disabled", "summary": {"updated": 0, "error": 0, "skipped": 1}}

    plan_actions = {action["source"]: action for action in plan.get("actions", []) if action.get("type") == "move"}
    move_results = [
        result
        for result in apply_result.get("results", [])
        if result.get("status") == "applied" and result.get("type") == "move"
    ]

    radarr_config = build_provider_config(integrations.get("radarr", {}))
    sonarr_config = build_provider_config(integrations.get("sonarr", {}))
    radarr_client = RadarrClient(radarr_config) if radarr_config.enabled else None
    sonarr_client = SonarrClient(sonarr_config) if sonarr_config.enabled else None

    root_error = ensure_provider_roots(radarr_client, sonarr_client, options)
    if root_error is not None:
        return root_error

    results: list[dict[str, Any]] = []
    for move in move_results:
        action = plan_actions.get(move["source"])
        if action is None:
            results.append({"status": "skipped", "source": move["source"], "reason": "missing_plan_action"})
            continue

        provider = provider_for_action(action)
        if provider == "radarr" and radarr_client:
            results.append(sync_radarr_movie(radarr_client, action, options))
        elif provider == "sonarr" and sonarr_client:
            results.append(sync_sonarr_series(sonarr_client, action, options))
        else:
            results.append({"status": "skipped", "source": move["source"], "reason": f"{provider}_disabled"})

    return {
        "status": "completed",
        "summary": summarize_sync_results(results),
        "results": results,
    }


def ensure_provider_roots(
    radarr_client: RadarrClient | None,
    sonarr_client: SonarrClient | None,
    options: dict[str, Any],
) -> dict[str, Any] | None:
    if options.get("create_root_folder_if_missing", True):
        if radarr_client and radarr_client.config.root_folder_path:
            try:
                radarr_client.ensure_root_folder(radarr_client.config.root_folder_path)
            except ProviderError as exc:
                return build_sync_error("radarr", exc)
        if sonarr_client and sonarr_client.config.root_folder_path:
            try:
                sonarr_client.ensure_root_folder(sonarr_client.config.root_folder_path)
            except ProviderError as exc:
                return build_sync_error("sonarr", exc)
    return None


def provider_for_action(action: dict[str, Any]) -> str:
    return "radarr" if str(action.get("media_key", "")).startswith("movie:") else "sonarr"


def sync_radarr_movie(client: RadarrClient, action: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    try:
        movie = match_radarr_movie(client.list_movies(), action)
        if movie is None:
            return {"status": "error", "provider": "radarr", "source": action["source"], "message": "movie not found"}

        movie["path"] = str(Path(action["destination"]).parent)
        target_root = action.get("details", {}).get("target_root") or client.config.root_folder_path
        if target_root:
            movie["rootFolderPath"] = target_root
        updated = client.update_movie(movie)
        refresh = None
        if options.get("rescan_after_update", True):
            refresh = client.refresh_movie(int(movie["id"]))
        return {
            "status": "updated",
            "provider": "radarr",
            "source": action["source"],
            "destination": action["destination"],
            "item_id": updated.get("id", movie.get("id")),
            "path": updated.get("path", movie.get("path")),
            "refresh": refresh,
        }
    except ProviderError as exc:
        return {"status": "error", "provider": "radarr", "source": action["source"], "message": str(exc)}


def sync_sonarr_series(client: SonarrClient, action: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    try:
        series = match_sonarr_series(client.list_series(), action)
        if series is None:
            return {"status": "error", "provider": "sonarr", "source": action["source"], "message": "series not found"}

        destination = Path(action["destination"])
        details = action.get("details", {})
        target_root = details.get("target_root") or client.config.root_folder_path
        series["path"] = str(compute_series_path(destination, target_root))
        if target_root:
            series["rootFolderPath"] = target_root
        updated = client.update_series(series)
        refresh = None
        if options.get("rescan_after_update", True):
            refresh = client.refresh_series(int(series["id"]))
        return {
            "status": "updated",
            "provider": "sonarr",
            "source": action["source"],
            "destination": action["destination"],
            "item_id": updated.get("id", series.get("id")),
            "path": updated.get("path", series.get("path")),
            "refresh": refresh,
        }
    except ProviderError as exc:
        return {"status": "error", "provider": "sonarr", "source": action["source"], "message": str(exc)}


def match_radarr_movie(movies: list[dict[str, Any]], action: dict[str, Any]) -> dict[str, Any] | None:
    source_parent = str(Path(action["source"]).parent.resolve())
    destination_parent = str(Path(action["destination"]).parent.resolve())
    title = normalize_title(action.get("details", {}).get("title", ""))
    year = action.get("details", {}).get("year")

    for movie in movies:
        movie_path = str(Path(movie.get("path", ".")).resolve())
        if movie_path in {source_parent, destination_parent}:
            return movie
    for movie in movies:
        if normalize_title(movie.get("title", "")) == title and movie.get("year") == year:
            return movie
    return None


def match_sonarr_series(series_list: list[dict[str, Any]], action: dict[str, Any]) -> dict[str, Any] | None:
    source = Path(action["source"]).resolve()
    destination = Path(action["destination"]).resolve()
    title = normalize_title(action.get("details", {}).get("title", ""))

    for series in series_list:
        series_path = Path(series.get("path", ".")).resolve()
        if is_relative_to(source, series_path) or is_relative_to(destination, series_path):
            return series
    for series in series_list:
        if normalize_title(series.get("title", "")) == title:
            return series
    return None


def compute_series_path(destination: Path, target_root: str | None) -> Path:
    resolved_destination = destination.resolve()
    if target_root:
        root = Path(target_root).resolve()
        if is_relative_to(resolved_destination, root):
            relative = resolved_destination.relative_to(root)
            if relative.parts:
                return root / relative.parts[0]
    if destination.parent.name.lower().startswith("season "):
        return destination.parent.parent
    return destination.parent


def normalize_title(value: str) -> str:
    return " ".join(str(value).lower().split())


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def summarize_sync_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"updated": 0, "error": 0, "skipped": 0}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary


def build_sync_error(provider: str, exc: ProviderError) -> dict[str, Any]:
    return {
        "status": "error",
        "summary": {"updated": 0, "error": 1, "skipped": 0},
        "results": [{"status": "error", "provider": provider, "message": str(exc)}],
    }


def normalize_base_url(value: str) -> str:
    normalized = value.rstrip("/")
    if normalized.endswith("/api/v3"):
        return normalized[: -len("/api/v3")]
    return normalized
