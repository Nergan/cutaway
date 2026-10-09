# Another VPN

> **Read this in another language:**  
> [English](README.md) | [Русская версия](README.ru.md)

The hub does not run or publish this directory.

**Another VPN** is a private, cross-platform, DPI-resistant circumvention and networking system engineered with a strict **Zero-Knowledge device identity** model, **Post-Quantum hybrid cryptography**, and a **custom lightweight userspace TCP/IP stack**.

The project is structured around a Hexagonal (Ports & Adapters) architecture across a polyglot monorepo (Go, TypeScript/Cloudflare Workers, Python/FastAPI, Flutter/Kotlin).

---

## Key Architectural Highlights

* **Pure Go Userspace TCP/IP NAT Stack (`netstack`)**: Does not rely on heavy dependencies like gVisor or lwIP. Directly processes raw L3 IPv4 packets from TUN devices, translates TCP 3-way handshakes, tracks Sequence/Ack numbers, manages TCP windowing, and multiplexes client connections into outbound VLESS streams.
* **Zero-Dependency Core Protocol Implementations**:
  * **RFC 6455 WebSocket Client (`wsproto`)**: Written from scratch over `net.Conn` without third-party libraries (e.g., `gorilla/websocket`).
  * **VLESS v0 Protocol (`vlessproto`)**: Clean-room implementation of the binary wire-format for both client and origin proxy.
  * **XTLS Reality Client & Origin Server**: Full client implementation utilizing `utls` for realistic Chrome TLS fingerprint mimicry, X25519 ECDH key exchange, HKDF, and AEAD encryption embedded inside TLS `SessionID`, plus an origin server with automatic probe-fallback to authentic donor websites.
  * **Split-HTTP (`xhttp`)**: Bidirectional streaming over decoupled HTTP/2 GET (downlink) and POST (uplink) channels.
* **Hybrid Post-Quantum Cryptography (ADR 0006)**:
  * **Client Identity**: Device identity pairs Ed25519 with **ML-DSA-65 (FIPS 204)** via Cloudflare `circl`.
  * **Admin Plane**: Authenticated operations require dual-signed payloads (Ed25519 + ML-DSA-65) validated against an append-only sequence/hash chain, eliminating replay and state-forking attacks without a blockchain.
* **Zero-Knowledge Device Enrollment**: Private keys are generated locally on the end-user device and never leave the device keystore (stored with `0600` permissions). Only public keys are registered via single-use enrollment tokens.
* **Multi-Tier Egress & Failover**:
  * **Tier 1 (Bootstrap)**: Serverless CDN-fronted transport (Cloudflare Worker WebSocket proxy using `cloudflare:sockets`).
  * **Tier 2 (Target)**: Dedicated high-throughput servers (VPS running XTLS Reality or Split-HTTP).
  * Automatic active RTT probing and failover to ensure connection survival under aggressive whitelist-based DPI.
* **OS-Level Routing & Resilient Kill Switch**:
  * **Windows**: Kernel driver via `wintun.dll` dynamically invoked through Win32 syscalls; route-based blackhole kill switch.
  * **Linux**: Native `/dev/net/tun` via `ioctl`; atomic packet filtering and control-plane bypassing via `nftables`.
  * **Android**: Integration with Android's `VpnService` via `gomobile` bindings.

---

## Monorepo Layout

```text
├── core/                   # Go 1.24 VPN Engine & Origin Sidecars
│   ├── cmd/
│   │   ├── desktop/        # Desktop runner (Local HTTP control API on 127.0.0.1:47821)
│   │   ├── mobilelib/      # Android/iOS gomobile bindings
│   │   ├── reality-origin/ # XTLS Reality standalone server & SNI prober
│   │   └── xhttp-origin/   # Split-HTTP origin server
│   └── internal/
│       ├── adapters/       # TUN, Kill Switch, Netstack, Transports, Keystore, Probing
│       ├── app/            # Application Use Cases (Connect, Disconnect, SwitchNode)
│       └── domain/         # Pure domain entities, hybrid identity, failover policy
├── edge/                   # Cloudflare Worker (Control Plane & Tier 1 Data Plane)
│   ├── src/
│   │   ├── adapters/       # Durable Object Nonce Store, KV Ban Cache, Session Store
│   │   ├── domain/         # Challenge-response logic, VLESS parser, Ban policy
│   │   └── handlers/       # Endpoints: /nonce, /auth, /enroll, /proxy, /xhttp
│   └── wrangler.toml       # Cloudflare Worker configuration & KV/DO bindings
├── control-plane-admin/    # Origin API, Admin Monitor & Distribution Portal (Python 3.12 / FastAPI)
│   ├── another_admin/
│   │   ├── adapters/       # Async Mongo store, Keyfile encryption, GitHub Dispatch
│   │   ├── api/            # Signed admin commands, internal edge proxy, user portal
│   │   └── domain/         # Anomaly detection, per-client installer builder
│   └── scripts/            # CI installer packager
├── app/                    # Multiplatform Client App (Flutter & Kotlin VpnService)
├── infra/                  # Infrastructure as Code
│   ├── cloudflare/         # Terraform configurations for Worker, KV, and DNS
│   └── generic-vps/        # Cloud-init & Compose configurations for VPS exit nodes
└── deploy/origin/          # Dockerfile & Compose for the unified Origin stack
```

---

## Cryptographic & Security Model

```text
                    [ Administrator ]
                            │
               Passphrase-wrapped Keyfile (.another-admin-key)
               Dual-sign: Ed25519 + ML-DSA-65 (FIPS 204)
               Sequence Counter + Hash-Chain
                            ▼
      ┌──────────────────────────────────────────────┐
      │  Control Plane API (FastAPI / PyMongo Async) │
      └──────────────────────┬───────────────────────┘
                             │
            Internal REST Proxy (Shared Secret)
                             ▼
      ┌──────────────────────────────────────────────┐
      │   Cloudflare Edge Worker (Tier 1 Gateway)    │
      └──────────────────────▲───────────────────────┘
                             │
     1. GET /nonce           │ 3. Sign: Ed25519(nonce || ts)
     2. Nonce issued (DO)    │ 4. POST /auth -> Session Ticket + VLESS UUID
                             │
                      [ Client Device ]
             Local Private Key Storage (Never Exported)
               Userspace L3 NAT -> VLESS WebSocket / Reality
```

1. **Anti-Replay**: The Edge Worker delegates nonces to a **Cloudflare Durable Object** (`NonceLedgerObject`), guaranteeing strict global consistency across all edge points-of-presence (PoPs).
2. **Device Identity**: Generated upon installation. The private key remains strictly on the device; enrollment maps the public key hash to an administrative profile stub.
3. **Session Tickets**: Successful challenge-response grants a short-lived bearer session token and an isolated VLESS user ID valid for proxy data streams.

---

## Testing & Quality Assurance

Each subsystem includes comprehensive isolated unit and integration suites:

```bash
# Go Core: Architecture, NAT stack, Reality, WebSocket, and Crypto tests
cd core && go test -v -race ./...

# Edge Worker: Domain protocol parser, ban policy, and verifier tests
cd edge && npm test

# Control Plane: Admin signature chains, anomaly detection, API tests
cd control-plane-admin && pytest
```

---

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL 2.0)**.  
Certain third-party components (such as Wintun) retain their respective original licenses (GPLv2).