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
    tier: Optional[int]
    max_connections: Optional[int]
    delinquent: Optional[bool]


def _optional_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
            tier=_optional_int(self._api.user_tier),
            max_connections=_optional_int(
                getattr(account, "max_connections", None)
            ),
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

        primary_value = get_primary_secret()
        if not isinstance(primary_value, str) or not primary_value:
            raise PrimaryAuthenticationFailed("Primary value is empty")

        try:
            result = await asyncio.wait_for(
                self._api.login(username.strip(), primary_value),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise AccountOperationTimeout("Proton sign-in timed out") from exc

        if not result.authenticated:
            raise PrimaryAuthenticationFailed("Primary flow failed")

        attempts = 0
        while result.twofa_required:
            if get_totp is None:
                raise SecondFactorRequired("A second factor is required")
            if attempts >= max_totp_attempts:
                raise SecondFactorFailed("Second-factor flow failed")

            second_value = get_totp()
            if not isinstance(second_value, str) or not second_value.strip():
                raise SecondFactorFailed("Second-factor value is empty")

            attempts += 1
            try:
                result = await asyncio.wait_for(
                    self._api.submit_2fa_code(second_value.strip()),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError as exc:
                raise AccountOperationTimeout(
                    "Second-factor flow timed out"
                ) from exc

            if not result.authenticated and not result.twofa_required:
                raise SecondFactorFailed("Second-factor flow failed")

        if not self.active:
            raise AccountError(
                "Proton reported successful sign-in without an active session"
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
