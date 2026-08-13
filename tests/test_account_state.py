import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from protonvpn_cli.account import AccountRequired, AccountService
from protonvpn_cli.constants import VERSION


class Refresher:
    def __init__(self):
        self.calls = 0

    async def get_up_to_date_server_list(self):
        self.calls += 1
        return ["server-a"]


class FakeAPI:
    def __init__(self, active=False):
        self._active = active
        self.login_calls = []
        self.logout_calls = 0
        self.refresher = Refresher()
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

    async def logout(self):
        self.logout_calls += 1
        self._active = False


def test_existing_session_supplies_account_metadata_without_new_login():
    api = FakeAPI(active=True)
    info = AccountService(api=api).info()
    assert info.name == "user@example.test"
    assert info.plan_title == "VPN Plus"
    assert info.tier == 2
    assert api.login_calls == []


def test_account_metadata_requires_active_session():
    with pytest.raises(AccountRequired):
        AccountService(api=FakeAPI()).info()


def test_server_refresh_reuses_current_session():
    api = FakeAPI(active=True)
    result = asyncio.run(AccountService(api=api).server_list())
    assert result == ["server-a"]
    assert api.refresher.calls == 1
    assert api.login_calls == []


def test_sign_out_is_idempotent():
    inactive = FakeAPI()
    asyncio.run(AccountService(api=inactive).sign_out())
    assert inactive.logout_calls == 0

    active = FakeAPI(active=True)
    asyncio.run(AccountService(api=active).sign_out())
    assert active.logout_calls == 1
    assert not active.is_user_logged_in()


def test_default_api_uses_project_version_metadata():
    fake_api = object()
    with patch("protonvpn_cli.account.ClientTypeMetadata") as metadata_cls, patch(
        "protonvpn_cli.account.ProtonVPNAPI", return_value=fake_api
    ) as api_cls:
        service = AccountService()
    metadata_cls.assert_called_once_with(type="cli", version=VERSION)
    api_cls.assert_called_once_with(client_type_metadata=metadata_cls.return_value)
    assert service._api is fake_api
