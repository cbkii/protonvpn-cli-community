"""Public CLI dispatcher for account/session migration."""

import argparse
import asyncio
import getpass
import json
import logging
import os
import sys
import tempfile
import time

from . import cli as legacy_cli
from . import utils
from .account_auth import AccountCommandError, open_account, sign_out_account
from .constants import CLIENT_SUFFIX, CONFIG_DIR, PASSFILE, SERVER_INFO_FILE, VERSION
from .secrets import AccountSecretStore, SecretStoreError


_SESSION = {"service": None}


class _RedactSecrets(logging.Filter):
    def __init__(self, values):
        super().__init__()
        self.values = values

    def filter(self, record):
        message = record.getMessage()
        for value in self.values:
            if value:
                message = message.replace(value, "***")
        record.msg = message
        record.args = ()
        return True


def _install_redaction(values):
    redactor = _RedactSecrets(values)
    for handler in legacy_cli.logger.handlers:
        handler.addFilter(redactor)


def _headless_environment():
    return bool(
        os.environ.get("PROTONVPN_USERNAME")
        and os.environ.get("PROTONVPN_PASSWORD")
    )


async def _open_service(username=None, primary_value=None, interactive=False):
    service = _SESSION.get("service")
    if service is not None and service.active:
        return service
    service = await open_account(
        username=username,
        primary_value=primary_value,
        interactive=interactive,
    )
    _SESSION["service"] = service
    return service


def _sync_account(service):
    info = service.info()
    if info.name:
        utils.set_config_value("USER", "username", info.name)
    if info.tier is not None:
        utils.set_config_value("USER", "tier", info.tier)
    utils.remove_config_value("USER", "password")
    return info


def _write_server_catalogue(server_list):
    if hasattr(server_list, "to_dict"):
        payload = server_list.to_dict()
    elif isinstance(server_list, dict):
        payload = server_list
    elif isinstance(server_list, list):
        payload = {"LogicalServers": server_list}
    else:
        raise AccountCommandError("Unsupported Proton server-list representation")

    os.makedirs(CONFIG_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".serverinfo.", dir=CONFIG_DIR)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(path, SERVER_INFO_FILE)
        path = ""
        os.chmod(SERVER_INFO_FILE, 0o600)
        utils.change_file_owner(SERVER_INFO_FILE)
    finally:
        if fd >= 0:
            os.close(fd)
        if path:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


async def _refresh_session(interactive=False):
    service = await _open_service(interactive=interactive)
    _sync_account(service)
    server_list = await service.server_list()
    _write_server_catalogue(server_list)
    utils.set_config_value("metadata", "last_api_pull", int(time.time()))
    return service


def _legacy_refresh(force=False, username=None, password=None):
    del force, username, password
    try:
        asyncio.run(_refresh_session(interactive=False))
        return True
    except (AccountCommandError, RuntimeError):
        return False


def _secure_hooks(store, redactions):
    original_get = utils.get_config_value
    original_set = utils.set_config_value
    original_metadata = utils.ClientTypeMetadata

    def secure_get(group, key):
        if group == "USER" and key == "password":
            saved = store.load()
            if saved is None:
                raise KeyError("password")
            return saved.password
        return original_get(group, key)

    def secure_set(group, key, value):
        if group == "USER" and key == "password":
            username = original_get("USER", "username")
            if not username or username == "None":
                saved = store.load()
                username = saved.username if saved is not None else None
            if not username:
                raise SecretStoreError("Cannot persist account secret without username")
            store.save(username, str(value))
            redactions.append(str(value))
            return
        if group == "USER" and key == "tier":
            service = _SESSION.get("service")
            if service is not None and service.active:
                authoritative = service.info().tier
                if authoritative is not None:
                    value = authoritative
        return original_set(group, key, value)

    def truthful_metadata(*args, **kwargs):
        kwargs["version"] = VERSION
        return original_metadata(*args, **kwargs)

    def safe_openvpn_credentials(write=True):
        username = os.environ.get("OPENVPN_USERNAME")
        value = os.environ.get("OPENVPN_PASSWORD")
        if not username:
            username = input("Enter your OpenVPN username: ").strip()
        if not value:
            first = getpass.getpass("Enter your OpenVPN password: ")
            second = getpass.getpass("Confirm your OpenVPN password: ")
            if first != second:
                raise SystemExit("OpenVPN passwords do not match")
            value = first
        if not username or not value:
            raise SystemExit("OpenVPN credentials are required")
        redactions.append(value)
        if write:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PASSFILE, "w", encoding="utf-8") as handle:
                handle.write(
                    "{0}+{1}\n{2}".format(username, CLIENT_SUFFIX, value)
                )
            os.chmod(PASSFILE, 0o600)
            utils.change_file_owner(PASSFILE)
            print("OpenVPN credentials have been updated!")
        return username, value

    def safe_account_credentials():
        username = os.environ.get("PROTONVPN_USERNAME")
        primary_value = os.environ.get("PROTONVPN_PASSWORD")
        interactive = not _headless_environment()
        if not username and interactive:
            username = input("Enter your ProtonVPN username: ").strip()
        if not primary_value and interactive:
            first = getpass.getpass("Enter your ProtonVPN password: ")
            second = getpass.getpass("Confirm your ProtonVPN password: ")
            if first != second:
                raise SystemExit("ProtonVPN passwords do not match")
            primary_value = first
        if not username or not primary_value:
            raise SystemExit("ProtonVPN account credentials are required")
        redactions.append(primary_value)
        service = asyncio.run(
            _open_service(
                username=username,
                primary_value=primary_value,
                interactive=interactive,
            )
        )
        _sync_account(service)
        return username, primary_value

    def authoritative_tier(write=False):
        service = asyncio.run(
            _open_service(interactive=not _headless_environment())
        )
        info = _sync_account(service)
        if info.tier is None:
            raise SystemExit("Proton did not return a valid account tier")
        title = info.plan_title or info.plan_name or "unknown"
        print("ProtonVPN plan: {0} (tier {1})".format(title, info.tier))
        if write:
            return info.tier
        return info.tier + 1

    utils.get_config_value = secure_get
    legacy_cli.get_config_value = secure_get
    utils.set_config_value = secure_set
    legacy_cli.set_config_value = secure_set
    utils.ClientTypeMetadata = truthful_metadata
    legacy_cli.set_openvpn_credentials_config = safe_openvpn_credentials
    legacy_cli.set_protonvpn_credentials_config = safe_account_credentials
    legacy_cli.set_protonvpn_tier = authoritative_tier
    utils.pull_server_data = _legacy_refresh
    legacy_cli.pull_server_data = _legacy_refresh


def _signin(argv):
    parser = argparse.ArgumentParser(prog="protonvpn signin")
    parser.add_argument("username", nargs="?")
    parser.add_argument("--username", dest="username_option")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    if args.username and args.username_option:
        parser.error("specify USERNAME either positionally or with --username, not both")
    username = args.username_option or args.username
    if args.replace:
        asyncio.run(sign_out_account(forget=True))
        _SESSION["service"] = None
    service = asyncio.run(
        _open_service(username=username, interactive=not _headless_environment())
    )
    info = _sync_account(service)
    print("Signed in as {0}.".format(info.name or username or "unknown"))
    print("Account secret stored in ~/.pvpn-cli/secrets/account.json (0600).")


def _signout(argv):
    parser = argparse.ArgumentParser(prog="protonvpn signout")
    parser.add_argument("--keep-secret", action="store_true")
    args = parser.parse_args(argv)
    asyncio.run(sign_out_account(forget=not args.keep_secret))
    _SESSION["service"] = None
    utils.remove_config_value("USER", "password")
    if args.keep_secret:
        print("Signed out; persisted account secret retained.")
    else:
        print("Signed out; persisted account secret removed.")


def _account(store, argv):
    parser = argparse.ArgumentParser(prog="protonvpn account")
    parser.add_argument(
        "action", nargs="?", choices=("info", "status"), default="info"
    )
    args = parser.parse_args(argv)
    saved = store.load()
    if args.action == "status":
        print("Persisted account secret: {0}".format("yes" if saved else "no"))
        if saved:
            print("Account: {0}".format(saved.username))
        return
    service = asyncio.run(
        _open_service(interactive=not _headless_environment())
    )
    info = _sync_account(service)
    print("Account: {0}".format(info.name or "unknown"))
    print("Plan: {0}".format(info.plan_title or info.plan_name or "unknown"))
    if info.tier is not None:
        print("Tier: {0}".format(info.tier))
    if info.max_connections is not None:
        print("Maximum connections: {0}".format(info.max_connections))


def _refresh(argv):
    if argv:
        raise SystemExit("usage: protonvpn refresh")
    asyncio.run(_refresh_session(interactive=not _headless_environment()))
    print("Server catalogue refreshed using the account session boundary.")


def main():
    store = AccountSecretStore()
    try:
        store.migrate_legacy_config()
        saved = store.load()
    except (SecretStoreError, ValueError) as exc:
        raise SystemExit("Unable to load account secret store: {0}".format(exc))

    redactions = []
    if saved is not None:
        redactions.append(saved.password)
    for variable in ("PROTONVPN_PASSWORD", "OPENVPN_PASSWORD"):
        value = os.environ.get(variable)
        if value:
            redactions.append(value)
    _install_redaction(redactions)
    _secure_hooks(store, redactions)

    argv = sys.argv[1:]
    command = argv[0] if argv else None
    try:
        if command == "signin":
            return _signin(argv[1:])
        if command == "signout":
            return _signout(argv[1:])
        if command == "account":
            return _account(store, argv[1:])
        if command == "refresh":
            return _refresh(argv[1:])
    except (AccountCommandError, SecretStoreError) as exc:
        raise SystemExit("Account operation failed: {0}".format(exc))

    legacy_init_args = any(
        flag in argv for flag in ("--password", "--openvpn-password", "--tier")
    )
    if command == "init" and legacy_init_args and not os.path.exists("/.dockerenv"):
        raise SystemExit(
            "Passwords and plan tier are no longer accepted on the command line; "
            "run 'protonvpn init' and use prompts or supported environment ingress."
        )
    return legacy_cli.main()
