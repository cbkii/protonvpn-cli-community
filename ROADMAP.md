# ProtonVPN CLI Community Modernisation Roadmap

## Product objective

Turn `cbkii/protonvpn-cli-community` into a dependable headless ProtonVPN client for Raspberry Pi and Linux servers that combines:

1. account/session access at the reliability standard of Proton's current CLI for simple username/password + optional TOTP flows;
2. the community CLI's broader headless/server-selection capabilities;
3. WireGuard-first transport;
4. continuous tunnel health supervision and automatic recovery;
5. robust Proton NAT-PMP/qBittorrent integration;
6. safe systemd-native long-running operation.

FIDO/U2F/security-key authentication is not part of the current scope.

## Current-state finding: account access is not yet at official-CLI standard

The current fork already calls Proton's `ProtonVPNAPI`, so it is not using a wholly custom authentication protocol. However, the surrounding account/session implementation is materially weaker than the current official CLI.

Current fork issues that make authentication/session handling P0 work:

- Proton account password is written into the normal configuration file.
- CLI setup accepts password values in process arguments.
- OpenVPN credentials are written to a passfile and the current code logs their contents.
- Server refresh reconstructs an API object and performs username/password authentication again rather than treating a persisted Proton session as the primary account state.
- The user manually supplies plan/tier during initialisation rather than treating authenticated account metadata as authoritative.
- client metadata is spoofed with version `99.99.99`.
- the project pins a personal `proton-vpn-api-core` fork based on 0.42.4 from April 2025; Proton's July 2026 stable CLI has moved to the newer API-core 5.5.5 generation.
- the repository has no dedicated authentication/session test suite; its current tests cover VPN health only.

By contrast, the current official stack uses a dedicated account lifecycle (`signin`, `signout`, account info), `ProtonSSO`/session persistence, account-derived tier data and current Proton session/refresher abstractions.

The goal is **behavioural parity for simple account access**, not wholesale adoption of the official CLI's desktop/networking architecture.

---

## P0 — Official-grade simple account/session foundation

### P0.1 Dependency and compatibility audit

Before changing behaviour:

- resolve the latest compatible `ProtonVPN/proton-vpn-cli`, `python-proton-vpn-api-core`, `python-proton-core` and `python-proton-keyring-linux` stable states;
- map which dependencies provide authentication/session persistence versus GUI/NetworkManager transport concerns;
- determine whether maintained upstream packages can replace the stale personal 0.42.4 fork without importing unwanted desktop requirements;
- establish a modern Python support baseline compatible with Debian 13/aarch64;
- add dependency/version compatibility tests or constraints so future Proton API-core upgrades are deliberate.

### P0.2 Introduce an account/session service boundary

Create a transport-independent account layer responsible for:

- loading current/default Proton session;
- username/password sign-in;
- optional TOTP challenge completion;
- session reuse;
- session refresh/recovery;
- account name and plan/tier metadata;
- sign-out/session deletion;
- mapped, user-friendly authentication errors.

VPN connection code must consume account/session results rather than reimplement login.

### P0.3 Replace `init`-style credential storage

Converge toward:

- `protonvpn signin [USERNAME]`
- `protonvpn signout`
- `protonvpn account [info|status]`

Retain `init` only as a temporary migration path if necessary.

Remove:

- Proton password from the normal config;
- normal `--password` argv flow;
- manual tier as authoritative account state;
- secret-bearing debug logs;
- arbitrary `99.99.99` client-version spoofing.

### P0.4 Headless persistent session strategy

Preserve ProtonSSO's core semantics: persisted sessions, advisory locking/concurrency safety, reload by account/default session, and session deletion on logout.

Test the maintained Proton keyring/session stack on a headless Debian environment. Do not require a graphical login/session merely for account persistence.

If the standard Linux keyring backend cannot operate appropriately headlessly, add the smallest maintainable project-owned persistence adapter that satisfies:

- no plaintext account password;
- strict ownership/mode;
- no secret logs;
- non-interactive reuse after first sign-in;
- deterministic unit/integration tests;
- clear migration and deletion behaviour.

Do not implement a new Proton authentication protocol when the Proton session libraries already handle it.

### P0.5 Authentication tests

Add deterministic tests for:

- correct password;
- wrong password;
- TOTP required;
- correct TOTP;
- invalid/expired TOTP;
- session persistence across processes;
- refresh of valid persisted session;
- expired/revoked session;
- transient network/API failure;
- logout/session deletion;
- account-derived plan/tier;
- no password/TOTP/session-token leakage to config, argv or logs;
- concurrent access/session locking where the persistence backend supports it.

Add an optional credentialed smoke workflow after deterministic coverage exists.

### P0 exit criteria

P0 is complete only when a normal user can sign in once, restart the program/host, continue to access account/server metadata without re-entering their password, receive a TOTP prompt only when Proton requires one, sign out cleanly, and no account password is retained in normal configuration/logs/process arguments.

---

## P1 — Repository and Python modernisation

- remove obsolete Python 3.5-era metadata and classifiers;
- establish supported Debian 12/13 + aarch64/x86-64 matrix;
- minimise stale Git-only dependency pins;
- consolidate configuration/state paths and permissions;
- define typed config/state models;
- improve lint/static/type/unit CI;
- make all network/API operations explicitly bounded.

P1 must not regress the P0 account contract.

---

## P2 — WireGuard-first connection backend

Introduce a clean `ConnectionBackend` contract and make WireGuard the primary supported backend.

Capabilities:

- import Proton `.conf` profiles;
- normalised profile inventory/metadata;
- clean up/down/reconnect lifecycle;
- explicit endpoint route handling;
- full-tunnel policy routing;
- bounded handshake wait;
- clean rollback on partial setup failure;
- optional OpenVPN compatibility backend only if maintaining it does not distort the new architecture.

Keep profile acquisition separate from profile execution.

---

## P3 — Connection state machine, health supervisor and failover

Introduce explicit states such as:

- disconnected;
- connecting;
- handshake-wait;
- verifying;
- connected;
- degraded;
- recovering;
- failed.

Layer health signals:

- interface/link state;
- route/policy state;
- WireGuard handshake existence;
- handshake age;
- tunnel-bound IP/ICMP or DNS probe;
- tunnel-bound TLS/HTTPS probe with multiple targets;
- optional public-IP/provider validation.

### Release-blocking regression

Reproduce the known `wgpn` failure:

- `wg0` exists/up;
- full-tunnel policy routing is installed;
- no successful handshake and RX remains zero;
- localhost qBittorrent responds;
- Internet is blackholed.

Expected behaviour:

- VPN is not reported healthy;
- health reason identifies the missing/stale tunnel signal;
- recovery begins promptly;
- failed endpoint receives a temporary health penalty/quarantine;
- another eligible endpoint is attempted with bounded retries;
- replacement is accepted only after handshake + traffic verification.

---

## P4 — nftables kill switch, routing and DNS

- replace legacy iptables backup/restore behaviour with application-owned nftables chains/table;
- atomic firewall updates;
- no ownership of unrelated firewall state;
- preserve configurable LAN management access;
- preserve route to selected WireGuard endpoint;
- explicit kill-switch modes/fail-closed semantics;
- resolver abstraction for `resolvconf`, `systemd-resolved` and supported static cases;
- leak and crash/restart tests.

---

## P5 — Proton server catalogue and selection

Retain/improve community-client capabilities:

- fastest;
- random;
- country/city;
- explicit server;
- P2P;
- future feature filters where supported.

Selection should combine Proton metadata with local health history:

- availability/status;
- provider score/load;
- RTT;
- recent success/failure;
- repeated handshake/health failures;
- recent-use penalty;
- capability requirements such as P2P/PF.

Expose explicit `balanced`, `latency/fastest` and `random` policies if useful.

---

## P6 — Proton NAT-PMP and qBittorrent

Implement NAT-PMP as an optional first-class subsystem:

- acquire TCP + UDP mapping;
- verify returned ports;
- maintain short lease before expiry;
- expose port-forward state separately from whole-VPN state.

Add an isolated qBittorrent adapter:

- bind to VPN interface/address;
- disable inappropriate random-port/UPnP behaviour when managing PF;
- apply current forwarded port;
- verify applied settings;
- verify TCP/UDP listeners;
- optional reannounce after port changes;
- remain fail-closed on VPN loss.

Local qB API availability must never count as VPN tunnel health.

---

## P7 — Headless daemon, IPC and systemd integration

Move privileged/network ownership into one authoritative service, tentatively:

- `protonvpn-communityd.service`

Keep `protonvpn` as the normal-user CLI communicating over protected local IPC.

Requirements:

- journald logging;
- bounded startup/shutdown;
- restart-safe state reconciliation;
- least privilege/capabilities;
- deliberate systemd hardening;
- optional local HTTP API implemented as an adapter over the same core, not by spawning CLI subprocesses;
- fast cached `status`; active probes in `health`/`diagnose`.

---

## P8 — Migration from `wgpn`

Provide a non-destructive migration flow such as:

- `protonvpn migrate wgpn --dry-run`
- `protonvpn migrate wgpn`
- validation of new stack;
- explicit `--disable-old` only after successful validation.

Import where practical:

- Proton WireGuard profiles;
- country/profile preferences;
- relevant server history;
- qBittorrent API/binding preferences;
- port-forward preferences;
- LAN/bypass policy.

Never silently delete old profiles/state. Document rollback.

---

## P9 — CI, release and operational qualification

Build deterministic tests using mocks and Linux network namespaces for:

- account/session lifecycle;
- WireGuard interface/route lifecycle;
- no-handshake blackhole;
- stale handshake;
- endpoint failure/failover;
- DNS failure;
- TLS probe failure;
- kill-switch leakage;
- daemon restart/stale state;
- NAT-PMP lease handling;
- qB API/binding/port failures;
- migration/idempotence.

CI should cover:

- unit/integration tests;
- formatting/lint/static typing;
- package build/install;
- systemd unit verification;
- ARM64-relevant build/package paths;
- optional live credentialed Proton smoke tests.

Live tests supplement deterministic failure-mode coverage; they are not a substitute.

---

## Reference implementations

Continue to compare current behaviour and concepts from:

- `ProtonVPN/proton-vpn-cli` — account lifecycle and current Proton-facing semantics;
- `ProtonVPN/python-proton-vpn-api-core` — Proton session/account facade;
- `ProtonVPN/python-proton-core` — ProtonSSO/session persistence and locking;
- `ProtonVPN/python-proton-keyring-linux` — official Linux secret/session backend approach;
- `ProtonVPN/proton-vpn-daemon` — privilege/service separation concepts;
- `passteque/gluetun` — continuous tunnel health, restart-on-failure, WireGuard reliability and Proton PF;
- `cbkii/wgpn` — useful profile/PF/qB/systemd concepts plus known failure modes to avoid;
- `tuiroot/protonvpn-random` — anti-stickiness/randomisation, validation and retry ideas;
- `WipeGuitarBranded/check-protonvpn` — tunnel-bound liveness checks, locking and PF renewal;
- `Delta-Kronecker/ProtonVPN-WireGuard-configuration` — automated profile inventory/provisioning concept only;
- `Chillsmeit/qBittorrent-ProtonVPN-Guide` — qB interface/port coupling;
- `binhex/arch-qbittorrentvpn` — fail-closed VPN/qB isolation concepts.

Resolve current upstream state before relying on any behaviour.

---

## Overall definition of success

A fresh supported headless Linux installation can:

1. sign in with username/password and optional TOTP;
2. persist/reuse a Proton session safely without storing the account password in normal config;
3. derive account/tier metadata authoritatively;
4. establish and verify a WireGuard tunnel;
5. detect an apparently-up but unusable tunnel promptly;
6. fail over to a healthy endpoint without corrupting host routing;
7. remain fail-closed where configured while preserving LAN administration;
8. maintain Proton port forwarding where enabled;
9. keep qBittorrent correctly bound and synchronised;
10. provide useful status/health/diagnose/JSON outputs;
11. operate automatically under systemd after reboot;
12. migrate from and roll back to the prior `wgpn` setup cleanly.
