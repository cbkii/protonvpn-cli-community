"""Transport-independent Proton account boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from proton.vpn.core.api import ProtonVPNAPI
from proton.vpn.core.session_holder import ClientTypeMetadata

from .constants import VERSION


class AccountError(RuntimeError):
    """Base error for account lifecycle failures."""


class AccountAlreadyActive(AccountError):
    pass


class AccountRequired(AccountError):
    pass


class PrimaryAuthenticationFailed(AccountError):
    pass


class SecondFactorRequired(AccountError):
    pass


class SecondFactorFailed(AccountError):
    pass


class AccountOperationTimeout(AccountError):
    pass


@dataclass(frozen=True)
class AccountInfo:
    name: Optional[str]
    plan_name: Optional[str]
    plan_title: Optional[str]
    tier: int
    max_connections: Optional[int]
    delinquent: Optional[bool]


class AccountService:
    """Owns Proton account/session access independently of VPN transport."""

    def __init__(self, api=None, timeout: float = 30.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._api = api or ProtonVPNAPI(
            client_type_metadata=ClientTypeMetadata(type="cli", version=VERSION)
        )
        self._timeout = float(timeout)

    @property
    def active(self) -> bool:
        return bool(self._api.is_user_logged_in())

    def require_active(self) -> None:
        if not self.active:
            raise AccountRequired("No Proton account is signed in")

    def info(self) -> AccountInfo:
        self.require_active()
        account = self._api.account_data
        return AccountInfo(
            name=self._api.account_name,
            plan_name=getattr(account, "plan_name", None),
            plan_title=getattr(account, "plan_title", None),
            tier=int(self._api.user_tier),
            max_connections=getattr(account, "max_connections", None),
            delinquent=getattr(account, "delinquent", None),
        )

    async def sign_in(
        self,
        username: str,
        get_primary_secret: Callable[[], str],
        get_totp: Optional[Callable[[], str]] = None,
        max_totp_attempts: int = 3,
    ) -> AccountInfo:
        if self.active:
            raise AccountAlreadyActive("A Proton account is already signed in")
        if not username or not username.strip():
            raise ValueError("username must not be empty")
        if max_totp_attempts < 1:
            raise ValueError("max_totp_attempts must be at least 1")

        try:
            result = await asyncio.wait_for(
                self._api.login(username.strip(), get_primary_secret()),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise AccountOperationTimeout("Proton sign-in timed out") from exc

        if not result.authenticated:
            raise PrimaryAuthenticationFailed("Proton authentication failed")

        attempts = 0
        while result.twofa_required:
            if get_totp is None:
                raise SecondFactorRequired("TOTP authentication is required")
            if attempts >= max_totp_attempts:
                raise SecondFactorFailed("TOTP authentication failed")
            attempts += 1
            try:
                result = await asyncio.wait_for(
                    self._api.submit_2fa_code(get_totp().strip()),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError as exc:
                raise AccountOperationTimeout("TOTP authentication timed out") from exc

            if not result.authenticated and not result.twofa_required:
                raise SecondFactorFailed("TOTP authentication failed")

        if not self.active:
            raise AccountError(
                "Proton reported successful authentication without an active session"
            )
        return self.info()

    async def server_list(self):
        self.require_active()
        try:
            return await asyncio.wait_for(
                self._api.refresher.get_up_to_date_server_list(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise AccountOperationTimeout("Proton server refresh timed out") from exc

    async def sign_out(self) -> None:
        if not self.active:
            return
        try:
            await asyncio.wait_for(self._api.logout(), timeout=self._timeout)
        except asyncio.TimeoutError as exc:
            raise AccountOperationTimeout("Proton sign-out timed out") from exc
