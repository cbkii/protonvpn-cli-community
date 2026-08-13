import asyncio

import pytest
from fastapi import HTTPException

from protonvpn_cli import api


def test_api_init_keeps_sensitive_values_out_of_argv(monkeypatch):
    captured = {}

    def fake_run(command, env=None):
        captured["command"] = command
        captured["env"] = env
        return {"success": True, "output": "ok"}

    monkeypatch.setattr(api, "run_cli_command", fake_run)
    request = api.InitRequest(
        username="person@example.test",
        password="account-value",
        tier=4,
        protocol="udp",
        force=True,
        openvpn_username="ovpn-user",
        openvpn_password="ovpn-value",
    )

    result = asyncio.run(api.initialize(request))

    assert result["success"] is True
    assert captured["command"] == ["protonvpn", "init", "--protocol", "udp", "--force"]
    assert "account-value" not in captured["command"]
    assert "ovpn-value" not in captured["command"]
    assert "4" not in captured["command"]
    assert captured["env"]["PROTONVPN_USERNAME"] == "person@example.test"
    assert captured["env"]["PROTONVPN_PASSWORD"] == "account-value"
    assert captured["env"]["OPENVPN_USERNAME"] == "ovpn-user"
    assert captured["env"]["OPENVPN_PASSWORD"] == "ovpn-value"


def test_api_init_requires_openvpn_bootstrap_pair(monkeypatch):
    monkeypatch.delenv("OPENVPN_USERNAME", raising=False)
    monkeypatch.delenv("OPENVPN_PASSWORD", raising=False)
    request = api.InitRequest(
        username="person@example.test",
        password="account-value",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(api.initialize(request))

    assert error.value.status_code == 400
