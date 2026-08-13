import os

from protonvpn_cli.secrets import AccountSecretStore


def test_secret_store_round_trip(tmp_path):
    path = tmp_path / "secrets" / "account.json"
    store = AccountSecretStore(str(path))
    store.save("user@example.test", "value")
    saved = store.load()
    assert saved.username == "user@example.test"
    assert saved.password == "value"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.stat(path.parent).st_mode & 0o777 == 0o700


def test_headless_environment_seeds_missing_store(tmp_path, monkeypatch):
    path = tmp_path / "secrets" / "account.json"
    store = AccountSecretStore(str(path))
    monkeypatch.setenv("PROTONVPN_USERNAME", "service@example.test")
    monkeypatch.setenv("PROTONVPN_PASSWORD", "service-value")

    assert store.bootstrap_from_environment() is True
    assert store.bootstrap_from_environment() is False

    saved = store.load()
    assert saved.username == "service@example.test"
    assert saved.password == "service-value"
    assert os.stat(path).st_mode & 0o777 == 0o600
