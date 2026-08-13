"""Public CLI compatibility layer for secure credential persistence."""

import argparse
import getpass
import logging
import os
import sys

from . import cli as legacy_cli
from . import utils
from .constants import CONFIG_DIR, PASSFILE
from .secrets import AccountSecretStore, SecretStoreError


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


def _secure_hooks(store, redactions):
    original_get = utils.get_config_value
    original_set = utils.set_config_value

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
        return original_set(group, key, value)

    def safe_openvpn_credentials(write=True):
        username = input("Enter your OpenVPN username: ").strip()
        first = getpass.getpass("Enter your OpenVPN password: ")
        second = getpass.getpass("Confirm your OpenVPN password: ")
        if first != second:
            raise SystemExit("OpenVPN passwords do not match")
        if not username or not first:
            raise SystemExit("OpenVPN credentials are required")
        redactions.append(first)
        if write:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PASSFILE, "w", encoding="utf-8") as handle:
                handle.write("{0}+f1\n{1}".format(username, first))
            os.chmod(PASSFILE, 0o600)
            utils.change_file_owner(PASSFILE)
            print("OpenVPN credentials have been updated!")
        return username, first

    utils.get_config_value = secure_get
    legacy_cli.get_config_value = secure_get
    utils.set_config_value = secure_set
    legacy_cli.set_config_value = secure_set
    legacy_cli.set_openvpn_credentials_config = safe_openvpn_credentials


def _signin(store, redactions, argv):
    parser = argparse.ArgumentParser(prog="protonvpn signin")
    parser.add_argument("--username")
    args = parser.parse_args(argv)
    username = args.username or input("Enter your ProtonVPN username: ").strip()
    first = getpass.getpass("Enter your ProtonVPN password: ")
    second = getpass.getpass("Confirm your ProtonVPN password: ")
    if first != second:
        raise SystemExit("ProtonVPN passwords do not match")
    if not username or not first:
        raise SystemExit("ProtonVPN username and password are required")

    store.save(username, first)
    redactions.append(first)
    utils.set_config_value("USER", "username", username)
    utils.remove_config_value("USER", "password")
    if not utils.pull_server_data(force=True):
        store.delete()
        raise SystemExit("Sign-in validation failed; stored secret was removed")
    print("Proton account credentials validated and stored securely.")


def _signout(store, argv):
    parser = argparse.ArgumentParser(prog="protonvpn signout")
    parser.add_argument("--keep-secret", action="store_true")
    args = parser.parse_args(argv)
    if not args.keep_secret:
        store.delete()
    utils.remove_config_value("USER", "password")
    if args.keep_secret:
        print("Local account session cleared; persisted secret retained.")
    else:
        print("Persisted Proton account secret removed.")


def _account(store, argv):
    if argv not in ([], ["info"]):
        raise SystemExit("usage: protonvpn account [info]")
    saved = store.load()
    if saved is None:
        raise SystemExit("No persisted Proton account secret. Run 'protonvpn signin'.")
    print("Account: {0}".format(saved.username))
    try:
        print("Tier: {0}".format(utils.get_config_value("USER", "tier")))
    except KeyError:
        print("Tier: unknown")
    print("Secret store: ~/.pvpn-cli/secrets/account.json")


def _refresh(argv):
    if argv:
        raise SystemExit("usage: protonvpn refresh")
    if not utils.pull_server_data(force=True):
        raise SystemExit("Server catalogue refresh failed")
    print("Server catalogue refreshed using persisted account credentials.")


def main():
    store = AccountSecretStore()
    try:
        store.migrate_legacy_config()
    except (SecretStoreError, ValueError) as exc:
        raise SystemExit("Unable to migrate legacy account secret: {0}".format(exc))

    redactions = []
    saved = store.load()
    if saved is not None:
        redactions.append(saved.password)
    _install_redaction(redactions)
    _secure_hooks(store, redactions)

    argv = sys.argv[1:]
    command = argv[0] if argv else None
    if command == "signin":
        return _signin(store, redactions, argv[1:])
    if command == "signout":
        return _signout(store, argv[1:])
    if command == "account":
        return _account(store, argv[1:])
    if command == "refresh":
        return _refresh(argv[1:])
    if command == "init" and any(
        flag in argv for flag in ("--password", "--openvpn-password", "--tier")
    ):
        raise SystemExit(
            "Passwords and plan tier are no longer accepted on the command line; "
            "run 'protonvpn init' and use the hidden prompts."
        )
    return legacy_cli.main()
