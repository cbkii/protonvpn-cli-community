import configparser

from protonvpn_cli.secrets import AccountSecretStore


def test_legacy_config_migration_removes_plaintext_field(tmp_path):
    cfg_path = tmp_path / "pvpn-cli.cfg"
    secret_path = tmp_path / "secrets" / "account.json"
    cfg = configparser.ConfigParser()
    cfg["USER"] = {"username": "user@example.test", "password": "value", "tier": "2"}
    with open(cfg_path, "w", encoding="utf-8") as handle:
        cfg.write(handle)
    store = AccountSecretStore(str(secret_path))
    assert store.migrate_legacy_config(str(cfg_path)) is True
    migrated = configparser.ConfigParser()
    migrated.read(cfg_path)
    assert not migrated.has_option("USER", "password")
    assert store.load().username == "user@example.test"
    assert store.load().password == "value"
