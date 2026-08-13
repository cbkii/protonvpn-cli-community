# Account sign-in and secret storage

## Normal CLI flow

```bash
sudo protonvpn signin USERNAME
sudo protonvpn account status
sudo protonvpn account info
sudo protonvpn refresh
sudo protonvpn signout
```

The account password is entered with a hidden prompt. TOTP is requested only when Proton requires it. `PROTONVPN_2FA` or `PROTONVPN_2FA_CODE` may be used for headless TOTP ingress.

`signout` removes the persisted account secret by default. Use `protonvpn signout --keep-secret` to retain it for later unattended reuse.

## Persistent account secret

The Proton account password is not stored in ordinary `~/.pvpn-cli/pvpn-cli.cfg` configuration. It is deliberately persisted at:

```text
~/.pvpn-cli/secrets/account.json
```

The secrets directory is mode `0700` and `account.json` is mode `0600`. Writes use a temporary file, `fsync`, and atomic replacement. The store is versioned for controlled future migration.

This file remains persistent so headless refresh/reconnect work can reuse the account after a process or host restart without requiring the password on every run.

## Migration

If an older `pvpn-cli.cfg` contains `[USER] password`, startup moves that value into the dedicated secret store and removes it from the ordinary config. An existing valid dedicated secret takes precedence.

Non-secret compatibility values such as username, protocol settings and Proton-derived tier may remain in the ordinary config.

## `init` compatibility

`protonvpn init` remains while the current OpenVPN transport still needs its separate OpenVPN account pair.

Legacy `--password`, `--openvpn-password`, and `--tier` arguments are no longer part of the normal initialization path. Interactive use relies on hidden prompts; service/container automation uses supported environment ingress. Plan/tier is obtained from authenticated Proton account metadata rather than selected manually.

OpenVPN credentials remain separate from the Proton account login and continue to use the restricted OpenVPN passfile required by the current transport backend.

## Headless/container ingress

Existing service/container variables remain valid input channels:

```text
PROTONVPN_USERNAME
PROTONVPN_PASSWORD
PROTONVPN_2FA
OPENVPN_USERNAME
OPENVPN_PASSWORD
```

When no persistent account secret exists, a complete Proton account pair from the environment seeds the restricted account file before legacy initialisation. Values are not copied into `pvpn-cli.cfg`.

The Docker bootstrap invokes `protonvpn init` with protocol/force controls only. Account credentials, OpenVPN credentials and plan tier are not copied into its command line.

The HTTP `/init` adapter similarly transfers bootstrap values to its child process through the environment rather than password-bearing CLI arguments. Its historical tier field remains accepted for compatibility but is ignored as an authority.

The Python dispatcher still recognises the historical all-argument form when invoked manually from an existing Docker environment as a short-term compatibility fallback, but the provided Docker bootstrap no longer uses it. Normal host CLI use rejects that form.

## Next phase

P0.4 should evaluate longer-lived Proton session/keyring persistence for headless Debian so routine account/server refreshes can reuse a maintained session more often. The restricted password file remains the durable fallback unless project policy is changed explicitly.
