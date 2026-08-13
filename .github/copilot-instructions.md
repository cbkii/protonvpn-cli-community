# Repository Copilot Instructions

Read `AGENTS.md` and `ROADMAP.md` before making changes. They are the authoritative product and engineering instructions for this fork.

The project target is a reliable headless, WireGuard-first ProtonVPN client for Debian/Raspberry Pi that preserves the useful breadth of the community CLI.

The current highest priority is **P0 account/session reliability**:

- match Proton's current CLI standard for username/password sign-in, optional TOTP 2FA, persistent session reuse, refresh/re-auth, account metadata and sign-out;
- FIDO/U2F/security-key support is explicitly out of scope unless later requested;
- never store the Proton account password in normal config;
- never log passwords, TOTP, session tokens, cookies, VPN private keys or qB credentials;
- never pass passwords/TOTP via normal command-line arguments;
- derive plan/tier from the authenticated account rather than user input;
- reuse/refresh a persisted Proton session instead of performing a fresh password login for routine server refresh;
- prefer maintained Proton session/SSO abstractions while keeping the project headless and transport-independent.

Do not begin a broad VPN-engine rewrite by preserving the current credential model. Complete or maintain the P0 contract first.

After P0, follow the roadmap for WireGuard lifecycle, health/failover, nftables/DNS, server selection, NAT-PMP/qBittorrent, daemon/systemd integration and `wgpn` migration.

A WireGuard interface being present/up is never sufficient evidence of VPN health. Preserve permanent regression coverage for the known predecessor failure where policy routing remained active but the tunnel had no handshake/RX and blackholed Internet traffic.

Before editing, resolve current repository/upstream state and inspect callers, tests, config, packaging, CI and docs affected by the change. Prefer bounded operations, deterministic tests and explicit failure states. Do not weaken safety/reliability behaviour just to make CI green.
