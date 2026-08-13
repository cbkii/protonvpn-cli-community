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
