"""Persistent secret storage for ProtonVPN CLI Community.

Secret material is intentionally kept out of the ordinary INI configuration.
The store is versioned, written atomically, and restricted to the owning user.
"""

from __future__ import annotations

import configparser
import json
import os
import pwd
import tempfile
from dataclasses import dataclass
from typing import Optional

from .constants import ACCOUNT_SECRETS_FILE, CONFIG_FILE, SECRETS_DIR, USER


class SecretStoreError(RuntimeError):
    """Raised when the persistent secret store cannot be read or written safely."""


@dataclass(frozen=True)
class AccountSecret:
    username: str
    password: str


class AccountSecretStore:
    """Versioned persistent storage for Proton account credentials."""

    VERSION = 1

    def __init__(self, path: str = ACCOUNT_SECRETS_FILE):
        self.path = path
        self.directory = os.path.dirname(path) or "."

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def load(self) -> Optional[AccountSecret]:
        if not self.exists():
            return None

        self._validate_mode(self.path)
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise SecretStoreError("Unable to read account secret store") from exc

        if payload.get("version") != self.VERSION:
            raise SecretStoreError("Unsupported account secret store version")

        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(username, str) or not username.strip():
            raise SecretStoreError("Account secret store has no valid username")
        if not isinstance(password, str) or not password:
            raise SecretStoreError("Account secret store has no valid password")

        return AccountSecret(username=username.strip(), password=password)

    def save(self, username: str, password: str) -> None:
        if not isinstance(username, str) or not username.strip():
            raise ValueError("username must not be empty")
        if not isinstance(password, str) or not password:
            raise ValueError("password must not be empty")

        self._ensure_directory()
        payload = {
            "version": self.VERSION,
            "username": username.strip(),
            "password": password,
        }

        fd = None
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                prefix=".account.", suffix=".tmp", dir=self.directory
            )
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                json.dump(payload, handle, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._set_owner(temp_path)
            os.replace(temp_path, self.path)
            temp_path = None
            os.chmod(self.path, 0o600)
            self._set_owner(self.path)
        except OSError as exc:
            raise SecretStoreError("Unable to write account secret store") from exc
        finally:
            if fd is not None:
                os.close(fd)
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    def delete(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SecretStoreError("Unable to delete account secret store") from exc

    def bootstrap_from_environment(self) -> bool:
        if self.exists():
            return False
        username = os.environ.get("PROTONVPN_USERNAME", "").strip()
        password = os.environ.get("PROTONVPN_PASSWORD", "")
        if not username or not password:
            return False
        self.save(username, password)
        return True

    def migrate_legacy_config(self, config_path: str = CONFIG_FILE) -> bool:
        """Move a legacy [USER] password entry into the dedicated secret store.

        Returns True when the ordinary config was changed. Existing valid secret
        data takes precedence, but the plaintext config password is still removed.
        """
        if not os.path.isfile(config_path):
            self.bootstrap_from_environment()
            return False

        config = configparser.ConfigParser()
        config.read(config_path)
        if not config.has_option("USER", "password"):
            self.bootstrap_from_environment()
            return False

        password = config.get("USER", "password", fallback="")
        username = config.get("USER", "username", fallback="")
        if password and password != "None" and not self.exists():
            self.save(username, password)

        config.remove_option("USER", "password")
        self._write_config_atomically(config, config_path)
        return True

    def _ensure_directory(self) -> None:
        try:
            os.makedirs(self.directory, mode=0o700, exist_ok=True)
            os.chmod(self.directory, 0o700)
            self._set_owner(self.directory)
        except OSError as exc:
            raise SecretStoreError("Unable to prepare secrets directory") from exc

    @staticmethod
    def _validate_mode(path: str) -> None:
        mode = os.stat(path).st_mode & 0o777
        if mode & 0o077:
            raise SecretStoreError(
                "Account secret store permissions are too broad; expected 0600"
            )

    @staticmethod
    def _write_config_atomically(config: configparser.ConfigParser, path: str) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        existing_mode = 0o600
        try:
            existing_mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            pass

        fd, temp_path = tempfile.mkstemp(prefix=".pvpn-cli.", dir=directory)
        try:
            os.fchmod(fd, existing_mode)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                config.write(handle)
                handle.flush()
                os.fsync(handle.fileno())
            AccountSecretStore._set_owner(temp_path)
            os.replace(temp_path, path)
            temp_path = ""
            os.chmod(path, existing_mode)
            AccountSecretStore._set_owner(path)
        finally:
            if fd >= 0:
                os.close(fd)
            if temp_path:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _set_owner(path: str) -> None:
        try:
            account = pwd.getpwnam(USER)
            stat_result = os.stat(path)
            if stat_result.st_uid == account.pw_uid and stat_result.st_gid == account.pw_gid:
                return
            if os.geteuid() == 0:
                os.chown(path, account.pw_uid, account.pw_gid)
        except (KeyError, FileNotFoundError):
            return


__all__ = [
    "AccountSecret",
    "AccountSecretStore",
    "SecretStoreError",
    "ACCOUNT_SECRETS_FILE",
    "SECRETS_DIR",
]
