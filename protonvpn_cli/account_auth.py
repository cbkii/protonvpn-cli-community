"""Account sign-in helpers for the public CLI."""

from __future__ import annotations

import getpass
import os

from .account import AccountError, AccountService
from .secrets import AccountSecretStore


class AccountCommandError(RuntimeError):
    pass


async def open_account(username=None, primary_value=None, interactive=False):
    """Return an authenticated AccountService, reusing persisted credentials.

    Environment variables are accepted as a non-interactive ingress for
    container/system service bootstrapping, but are never written to argv or
    ordinary configuration. The validated primary value is persisted through
    AccountSecretStore for later headless reuse.
    """
    service = AccountService()
    if service.active:
        return service

    store = AccountSecretStore()
    stored = store.load()

    if username is None:
        username = os.environ.get("PROTONVPN_USERNAME")
    if primary_value is None:
        primary_value = os.environ.get("PROTONVPN_PASSWORD")

    if username is None and stored is not None:
        username = stored.username
    if primary_value is None and stored is not None and username == stored.username:
        primary_value = stored.password

    if not username and interactive:
        username = input("Enter your ProtonVPN username: ").strip()
    if primary_value is None and interactive:
        primary_value = getpass.getpass("Enter your ProtonVPN password: ")
    if not username or not primary_value:
        raise AccountCommandError(
            "Stored, environment, or interactive Proton credentials are required"
        )

    def primary_secret():
        return primary_value

    def second_factor():
        code = os.environ.get("PROTONVPN_2FA") or os.environ.get(
            "PROTONVPN_2FA_CODE"
        )
        if code:
            return code
        return getpass.getpass("2FA Token: ") if interactive else ""

    try:
        await service.sign_in(
            username=username,
            get_primary_secret=primary_secret,
            get_totp=second_factor,
        )
    except AccountError as exc:
        raise AccountCommandError(str(exc)) from exc

    store.save(username, primary_value)
    return service


async def sign_out_account(forget=True):
    service = AccountService()
    try:
        await service.sign_out()
    except AccountError as exc:
        raise AccountCommandError(str(exc)) from exc
    if forget:
        AccountSecretStore().delete()
