import asyncio
from types import SimpleNamespace

import pytest

from protonvpn_cli.account import AccountService, PrimaryAuthenticationFailed


class Result:
    authenticated = True
    twofa_required = False


class API:
    def __init__(self):
        self._active = False
        self.calls = []
        self.account_name = "user@example.test"
        self.user_tier = 2
        self.account_data = SimpleNamespace(
            plan_name="vpn2024",
            plan_title="VPN Plus",
            max_connections=10,
            delinquent=False,
        )

    def is_user_logged_in(self):
        return self._active

    async def login(self, username, value):
        self.calls.append((username, value))
        self._active = True
        return Result()


def test_basic_sign_in_uses_callback_and_returns_account_data():
    api = API()
    info = asyncio.run(
        AccountService(api=api).sign_in(" user@example.test ", lambda: "value")
    )
    assert api.calls == [("user@example.test", "value")]
    assert info.tier == 2


def test_empty_primary_value_is_rejected_before_api_call():
    api = API()
    with pytest.raises(PrimaryAuthenticationFailed):
        asyncio.run(AccountService(api=api).sign_in("user@example.test", lambda: ""))
    assert api.calls == []
