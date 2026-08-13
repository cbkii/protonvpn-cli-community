import asyncio
from types import SimpleNamespace

import pytest

from protonvpn_cli.account import AccountService, SecondFactorRequired


class Result:
    authenticated = True
    twofa_required = True


class API:
    def __init__(self):
        self.account_name = "user@example.test"
        self.user_tier = 2
        self.account_data = SimpleNamespace()

    def is_user_logged_in(self):
        return False

    async def login(self, _username, _value):
        return Result()


def test_second_factor_provider_is_required_when_requested():
    with pytest.raises(SecondFactorRequired):
        asyncio.run(AccountService(api=API()).sign_in("u", lambda: "value"))
