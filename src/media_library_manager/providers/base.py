from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class ProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class ProviderConfig:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    root_folder_path: str = ""


class JsonApiClient:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, query=query)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload=payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PUT", path, payload=payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        if not self.config.base_url or not self.config.api_key:
            raise ProviderError("Missing base URL or API key.")

        url = self._build_url(path, query=query)
        body = None
        headers = {
            "Accept": "application/json",
            "X-Api-Key": self.config.api_key,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=20) as response:
                response_body = response.read()
        except error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"{method} {path} failed: {exc.code} {response_text}") from exc
        except error.URLError as exc:
            raise ProviderError(f"{method} {path} failed: {exc.reason}") from exc

        if not response_body:
            return {}
        return json.loads(response_body.decode("utf-8"))

    def _build_url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        if not query:
            return url
        return f"{url}?{parse.urlencode(query)}"
