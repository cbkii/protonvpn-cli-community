# Agent Instructions

## Mission

Evolve `cbkii/protonvpn-cli-community` into a reliable, headless, WireGuard-first ProtonVPN client for Linux servers and Raspberry Pi systems while preserving the useful breadth and scriptability of the community CLI.

The target product should combine:

- official-grade **simple account access**: username/password, optional TOTP 2FA, persistent session reuse, account metadata, refresh/re-auth and sign-out;
- the community CLI's broader server selection, automation and headless usability;
- robust WireGuard lifecycle, health supervision and automatic recovery;
- systemd-native operation on Debian/Raspberry Pi without a desktop session.

Read `ROADMAP.md` before making architectural changes.

## P0: account and session foundation

Account access is the first release gate. Do not start a large transport rewrite on top of the current credential model.

### Required account capabilities

Implement behaviour equivalent in reliability to the current official Proton VPN CLI for the supported simple flows:

- username/password sign-in;
- non-echoing password prompt by default;
- optional TOTP 2FA when required by the account;
- persistent authenticated session reuse across CLI invocations and reboot where supported by the Proton session stack;
- session refresh and clean re-authentication when a session is genuinely expired/revoked;
- authoritative account name, plan/tier and relevant account metadata from the authenticated Proton session;
- explicit sign-out that clears local session credentials/state;
- clear distinction between invalid credentials, TOTP-required, invalid/expired TOTP, expired/revoked session and transient network/API failure.

### Explicitly out of scope

Do not implement FIDO/U2F/security-key authentication unless a later requirement explicitly adds it. TOTP is sufficient for the current product.

### Secret-handling rules

- Never persist the Proton account password in the normal configuration file.
- Never log Proton passwords, TOTP values, refresh/session tokens, cookies, WireGuard private keys, OpenVPN credentials or qBittorrent credentials.
- Never put passwords or TOTP values in normal process arguments.
- Remove any existing logging that prints secret-bearing files or values.
- Non-interactive automation must use a deliberate secret-input mechanism rather than `--password` argv exposure.
- Do not require the user to declare their Proton plan/tier when it can be derived from the authenticated account.
- Do not spoof arbitrary client versions such as `99.99.99`; send truthful project/client metadata compatible with Proton's supported session stack.

### Session architecture

Prefer Proton-maintained account/session abstractions such as `ProtonSSO`, `VPNSession`, `ProtonVPNAPI` and their refresh mechanisms when they can be used headlessly.

Do not perform a fresh username/password login merely to refresh the server list when a valid persisted session can be reused or refreshed.

Keep authentication independent from the VPN transport backend. Account sign-in/session state must not depend on OpenVPN, WireGuard, NetworkManager, qBittorrent or the optional HTTP API.

The official Linux stack uses Proton SSO/keyring-based session persistence and advisory locking. This project must preserve equivalent session semantics while remaining usable on a headless Debian/Raspberry Pi host. Before choosing a storage backend, verify how the current Proton keyring/session stack behaves without a desktop keyring daemon. Prefer a maintained Proton-supported backend where practical; otherwise introduce only a narrow, permission-restricted headless persistence adapter. Never fall back to storing the account password in plaintext.

### Account commands

Converge on a clear account lifecycle, for example:

- `protonvpn signin [USERNAME]`
- `protonvpn signout`
- `protonvpn account` or `protonvpn account info`
- `protonvpn account status --json`

Legacy `init` may remain temporarily as a migration wrapper, but it must not remain the long-term account/authentication contract.

### Authentication acceptance tests

P0 is incomplete until deterministic tests cover at least:

- successful username/password sign-in;
- invalid password;
- TOTP-required sign-in;
- valid TOTP;
- invalid/expired TOTP;
- persisted-session reuse without requesting the password again;
- session refresh;
- expired/revoked session requiring re-authentication;
- transient API/network failure without destroying a still-valid stored session;
- account/tier metadata loaded from the authenticated session;
- sign-out and local session cleanup;
- secret-redaction/no-secret-logging assertions;
- command/API inputs do not expose account passwords through argv.

Credentialed live smoke tests may supplement these tests but never replace deterministic coverage.

## Architectural direction after P0

The supported target is a headless, WireGuard-first architecture with explicit components for:

- account/session management;
- Proton server catalogue and metadata refresh;
- WireGuard profile acquisition/import;
- server selection/scoring;
- WireGuard connection lifecycle;
- health supervision and automatic recovery;
- routing and nftables kill switch;
- DNS integration;
- Proton NAT-PMP port forwarding;
- optional qBittorrent integration;
- persistent non-secret operational state;
- CLI and optional local API/IPC.

## Reliability invariant: an interface is not a connection

A configured/up `wg0` interface must never by itself mean VPN healthy.

The project has a known real-world predecessor failure: full-tunnel policy routing remained installed while WireGuard had no successful handshake and received zero bytes, blackholing Internet traffic. The local qBittorrent API remained reachable. This must become permanent regression coverage.

A healthy connection must require bounded verification such as:

- expected interface/link state;
- expected route/policy state;
- non-zero WireGuard handshake;
- acceptable handshake age;
- tunnel-bound IP/ICMP or DNS probe;
- tunnel-bound TLS/HTTPS probe with fallback targets.

A missing/stale handshake or failed tunnel probe must trigger recovery even if local services are healthy.

## Recovery and server health

Core liveness belongs in the long-running service/supervisor, not a slow maintenance timer.

Use bounded retries, backoff/jitter, endpoint health history and temporary penalties/quarantine. Do not leave a proven-dead full-tunnel route active indefinitely.

Server selection should combine, where useful:

- Proton availability/status;
- Proton score/load;
- requested country/city/features;
- P2P/port-forward capability;
- measured RTT;
- recent health/connect failures;
- recent success history;
- anti-stickiness/recent-use penalty.

Keep explicit deterministic selection available. Random selection is a strategy, not a health mechanism.

## WireGuard profiles

Imported Proton WireGuard `.conf` files are a first-class supported source.

Keep profile acquisition separate from connection execution behind a small provider interface so refresh mechanisms can evolve independently.

Do not make Selenium, Chrome, Telegram, GitHub Actions or Proton dashboard scraping core runtime dependencies. They may only exist as optional provisioning adapters if ever needed.

Never log WireGuard private keys.

## Firewall, routing and DNS

- Prefer an application-owned nftables table/chains with atomic changes.
- Never flush or replace unrelated host firewall rules.
- Preserve configurable LAN administration access and the physical route required to reach the selected WireGuard endpoint.
- Make kill-switch modes and fail-closed semantics explicit.
- Do not blindly rewrite `/etc/resolv.conf`; detect the host resolver mechanism and use bounded adapters such as `resolvconf` and `systemd-resolved` where applicable.

## Proton NAT-PMP and qBittorrent

Port forwarding is optional and must not define whole-VPN health unless configuration explicitly requires it.

For Proton NAT-PMP:

- manage the short lease continuously;
- renew before expiry;
- validate TCP and UDP mappings;
- expose clear PF state and errors.

For qBittorrent:

- keep the integration optional and isolated;
- bind qBittorrent to the VPN interface/address so tunnel loss fails closed;
- update and verify its listen port after NAT-PMP changes;
- never treat localhost qBittorrent API reachability as evidence that the VPN tunnel is healthy.

## systemd and privilege model

Prefer systemd for long-running operation.

The target architecture should use one authoritative privileged service, tentatively `protonvpn-communityd`, for network state and an unprivileged `protonvpn` CLI communicating over protected local IPC. Avoid naming collisions with Proton's official daemon.

Apply least privilege and systemd hardening only after required capabilities and writable paths are understood and tested. Use journald by default.

## CLI and API behaviour

Preserve a concise, scriptable `protonvpn` command.

`status` should read authoritative cached state quickly. Active probes belong in `health`/`diagnose`.

Provide stable `--json` output where practical.

If the HTTP API remains, make it an adapter over the same core/daemon interface rather than spawning CLI subprocesses. Default it to local-only access.

## Packaging and compatibility

Primary deployment target:

- Debian 13 / Raspberry Pi OS-compatible Linux;
- aarch64 Raspberry Pi 5;
- headless operation;
- x86-64 Linux retained where practical.

Modernise legacy Python declarations and stale dependency pins deliberately. Do not add a mandatory GUI, desktop session, NetworkManager GUI or Docker dependency.

Prefer maintained reproducible dependencies. Avoid indefinite dependence on stale personal forks when maintained upstream components or a small local abstraction can provide the needed contract.

## Reference projects

When relevant, study current implementations and concepts in:

- `cbkii/protonvpn-cli-community`
- `cbkii/wgpn`
- `ProtonVPN/proton-vpn-cli`
- `ProtonVPN/proton-vpn-daemon`
- `ProtonVPN/python-proton-vpn-api-core`
- `ProtonVPN/python-proton-core`
- `ProtonVPN/python-proton-keyring-linux`
- `passteque/gluetun`
- `tuiroot/protonvpn-random`
- `WipeGuitarBranded/check-protonvpn`
- `Delta-Kronecker/ProtonVPN-WireGuard-configuration`
- `Chillsmeit/qBittorrent-ProtonVPN-Guide`
- `binhex/arch-qbittorrentvpn`

Use these as evidence/design references, not templates to copy wholesale. Resolve current upstream state before relying on behaviour that may have changed.

## Engineering workflow

Before changing code:

1. Read this file and `ROADMAP.md`.
2. Resolve the current default-branch head, open work, CI state and repository instructions.
3. Inspect affected callers, tests, configuration, packaging, service files and documentation.
4. Distinguish confirmed behaviour from assumptions.

While implementing:

- work in dependency-ordered coherent batches;
- keep blocking/network operations bounded with explicit timeouts;
- prefer typed Python modules for non-trivial stateful logic;
- keep secret-bearing and privileged operations narrowly scoped;
- add regression coverage with each behaviour change;
- do not weaken tests, security controls or failure handling merely to make CI green;
- continue with deterministic fixtures/network namespaces when live Proton credentials, a physical Pi or an external service are unavailable, and record only the remaining live qualification.

Before finishing:

- run relevant unit/integration/static/package checks;
- inspect the final current-head diff for scope creep;
- verify documentation matches implemented behaviour;
- check current CI and actionable review feedback;
- clearly record any unverified physical/live Proton qualification.

## Change control

- Do not silently delete existing user VPN profiles, credential/session stores, firewall configuration or `wgpn` state.
- Migration from `wgpn` must be non-destructive, support dry-run, validate the new stack before disabling the old one, and provide rollback.
- Do not introduce a second independent networking authority for qBittorrent, port forwarding or the VPN route without an explicit architectural need.
