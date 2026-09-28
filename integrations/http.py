from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Optional

import requests


class IntegrationError(RuntimeError):
    pass


class CachedJsonClient:
    def __init__(
        self,
        *,
        user_agent: str,
        cache_dir: Path,
        min_interval: float = 1.0,
        ttl_seconds: int = 7 * 24 * 3600,
        timeout: float = 15.0,
        retries: int = 3,
        secret_params: tuple = (),
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self.ttl = ttl_seconds
        self.timeout = timeout
        self.retries = retries
        self.secret_params = set(secret_params)
        self._last_call = 0.0

    def _cache_path(self, url: str, params: Mapping[str, Any]) -> Path:
        public = {k: v for k, v in sorted(params.items()) if k not in self.secret_params}
        digest = hashlib.sha1(json.dumps([url, public], sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> Optional[dict]:
        try:
            if time.time() - path.stat().st_mtime > self.ttl:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _wait(self) -> None:
        remaining = self.min_interval - (time.monotonic() - self._last_call)
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()

    def get_json(
        self, url: str, params: Optional[Mapping[str, Any]] = None, *, error_key: Optional[str] = None
    ) -> dict:
        params = dict(params or {})
        path = self._cache_path(url, params)
        cached = self._read_cache(path)
        if cached is not None:
            return cached

        last_error: Optional[Exception] = None
        for attempt in range(self.retries):
            self._wait()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = IntegrationError(f"HTTP {response.status_code} from {url}")
                time.sleep(2 ** attempt * 2)
                continue
            if response.status_code >= 400:
                raise IntegrationError(f"HTTP {response.status_code} from {url}: {response.text[:200]}")
            try:
                data = response.json()
            except ValueError as exc:
                raise IntegrationError(f"Invalid JSON from {url}") from exc
            if error_key and isinstance(data, dict) and error_key in data:
                raise IntegrationError(str(data.get("message") or data[error_key]))
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            return data
        raise IntegrationError(f"Giving up on {url}: {last_error}")
