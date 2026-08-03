"""Server-side Upstox token persistence."""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings


class TokenStoreError(RuntimeError):
    """Raised when token persistence fails."""


class TokenStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._token: dict[str, Any] | None = None
        self._load_error: str | None = None
        self.load_token()

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load_token(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._path.exists():
                self._token = None
                self._load_error = None
                return None

            try:
                with self._path.open("r", encoding="utf-8") as token_file:
                    token = json.load(token_file)
            except (OSError, json.JSONDecodeError) as exc:
                self._token = None
                self._load_error = str(exc)
                return None

            if not isinstance(token, dict):
                self._token = None
                self._load_error = "token file did not contain a JSON object"
                return None

            self._token = token
            self._load_error = None
            return deepcopy(self._token)

    def save_token(self, token: dict[str, Any]) -> None:
        if not token.get("access_token"):
            raise TokenStoreError("token response did not include access_token")

        token_to_store = deepcopy(token)
        token_to_store["_saved_at"] = datetime.now(UTC).isoformat()

        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = self._path.with_name(f".{self._path.name}.tmp")
                with temp_path.open("w", encoding="utf-8") as token_file:
                    json.dump(token_to_store, token_file, indent=2, sort_keys=True)
                    token_file.write("\n")
                os.chmod(temp_path, 0o600)
                temp_path.replace(self._path)
            except OSError as exc:
                raise TokenStoreError(str(exc)) from exc

            self._token = token_to_store
            self._load_error = None

    def get_token(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._token)

    def get_public_profile(self) -> dict[str, Any] | None:
        token = self.get_token()
        if token is None:
            return None
        token.pop("access_token", None)
        token.pop("extended_token", None)
        return token

    def is_connected(self) -> bool:
        token = self.get_token()
        return bool(token and token.get("access_token"))

    def delete_token(self) -> None:
        with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError as exc:
                raise TokenStoreError(str(exc)) from exc
            self._token = None
            self._load_error = None


token_store = TokenStore(settings.upstox_access_token_file)


def save_token(token: dict[str, Any]) -> None:
    token_store.save_token(token)


def load_token() -> dict[str, Any] | None:
    return token_store.load_token()


def is_connected() -> bool:
    return token_store.is_connected()
