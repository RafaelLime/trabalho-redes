# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a **scaffold**. The architecture, class structure, type hints, and
docstrings are complete, but most method bodies raise `NotImplementedError` with
a `TODO:` describing what to implement. The work to be done — and how each piece
maps to the graded rubric — lives in **`TODO.md`** (the canonical
implementation checklist). Read it before implementing any feature.

The goal is a **peer-to-peer (P2P) chat client** (course assignment for a
Networks class). Each peer registers with a central **Rendezvous server**,
discovers other peers, opens **direct persistent TCP connections** to them, and
exchanges chat messages. There is **no relay and no multi-hop** — `ttl` is fixed
at `1` on every P2P message and never decrements.

## Running

```bash
python3 main.py --config config.json   # --config is optional; defaults to config.json
```

- **Requires Python 3.9+** (uses `from __future__ import annotations` with PEP
  604 `X | None` hints). Developed/tested on 3.13.
- **No external dependencies** — standard library only (`socket`, `threading`,
  `json`, `logging`, `argparse`, `uuid`, `dataclasses`, `enum`, `datetime`,
  `shlex`). There is no `requirements.txt`, virtualenv, or build step needed.
- **No test framework** is configured. There is no `pytest`/`unittest` suite;
  validation is done via the manual test scenarios in `TODO.md` (e.g. run two
  peers with different `name`/`listen_port` and exercise the CLI).

Running two local peers: copy `config.json` to two files with distinct `name`
and `listen_port`, then launch `python3 main.py --config <each>` in separate
terminals.

## Configuration

All runtime parameters come from a JSON config (`config.json`), validated for
required keys in `main.py` (`REQUIRED_KEYS`). The default points at the public
test Rendezvous server `pyp2p.mfcaetano.cc:8080`. Protocol docs for that server:
<https://github.com/mfcaetano/pyp2p-rdv>.

## Architecture

`P2PClient` (`p2p_client.py`) is the orchestrator: it owns one instance of every
subsystem, wires them together with callbacks, and runs the lifecycle
(`start` / `stop`). `main.py` loads config, sets up logging, constructs the
client, then hands control to the blocking `CLI` loop.

**Subsystems** (each is a separate module, intentionally — modularity is a
graded requirement):

- `rendezvous_connection.py` — `RendezvousConnection`. Talks to the Rendezvous
  server. Each REGISTER/DISCOVER/UNREGISTER opens a **short-lived TCP connection**
  (send one JSON line, read one response, close). Also runs a background thread
  that re-sends REGISTER (~every `ttl/2`) to renew the TTL before it expires.
- `peer_connection.py` — `PeerServer` (listening socket, accept loop) +
  `PeerConnection` (one per peer link, inbound or outbound). Owns the
  HELLO/HELLO_OK handshake, `\n`-delimited framing, a **per-connection reader
  thread**, and thread-safe `send` (lock per socket).
- `peer_table.py` — `PeerTable` / `PeerEntry`. Thread-safe registry of known
  peers keyed by `peer_id`, holding per-peer `PeerState`, the active connection,
  and reconnection backoff state. Implements discovery merge (new vs. known),
  the **dedupe rule** (`should_dial`), and exponential backoff.
- `message_router.py` — `MessageRouter`. Application messaging: SEND (unicast,
  with ACK + 5s timeout tracking), PUB (namespace-cast `#ns` / broadcast `*`),
  and handling inbound SEND/ACK/PUB.
- `keep_alive.py` — `KeepAlive`. Background thread sending PING every
  `ping_interval`s to each active connection, matching PONG by `msg_id` to
  compute RTT, and marking non-responsive peers `STALE`.
- `cli.py` — `CLI`. Blocking stdin loop translating `/`-commands into client
  calls (`/peers`, `/msg`, `/pub`, `/conn`, `/rtt`, `/reconnect`, `/log`,
  `/quit`).
- `validation.py` — field validators (name/namespace ≤ 64 chars, port 1–65535,
  ttl 1–86400) run before REGISTER and on CLI input; plus basic inbound-message
  validation.

**`state.py` is the shared-definitions hub** — it has no network logic, only
protocol constants (`MAX_MSG_SIZE` = 32 KiB, `P2P_TTL` = 1, `PROTOCOL_VERSION`,
validation limits), the enums (`MsgType`, `RdvType`, `PeerState`, `Direction`),
and small helpers (`make_peer_id`, `split_peer_id`, `new_msg_id`,
`utc_timestamp`, and the `encode_line`/`decode_line` wire (de)serializers). Most
other modules import from it; put new shared constants/enums/helpers here.

### Message flow (the part that spans files)

Inbound: `PeerServer` accepts a socket → calls `P2PClient._on_accept` → creates
an inbound `PeerConnection`. Each `PeerConnection`'s reader thread parses a line
and invokes its `on_message` callback, which is `P2PClient._on_message`. That
method is the central **dispatch point**: it routes by `msg["type"]` to
`keep_alive` (PING/PONG), `router` (SEND/ACK/PUB), or handles HELLO/BYE itself.
Outbound is symmetric via `P2PClient.connect_to`. When a connection closes,
`PeerConnection` calls `on_close` → `P2PClient._on_conn_close`, which updates
`PeerTable` state and may schedule reconnection.

### Concurrency model

Heavily threaded, all daemon threads coordinated by `P2PClient`: the accept
thread, one reader thread per `PeerConnection`, the periodic DISCOVER loop, the
KeepAlive PING loop, and the Rendezvous TTL-renew loop. Shared state is guarded
by locks (`PeerTable._lock`, per-socket `_send_lock`, router/keep-alive locks);
preserve this thread-safety when adding code. Threads stop via `threading.Event`
(`_stop`) flags — honor them in any new loop.

### Wire protocol invariants (from the spec)

- Transport TCP; messages are **JSON UTF-8, one per line, `\n`-delimited**, max
  **32 KiB** — reject longer lines.
- Every P2P message carries `ttl: 1`; it does not decrement or get forwarded.
- `peer_id` is `name@namespace`. Send scopes: unicast `peer_id`, namespace-cast
  `#namespace`, broadcast `*`.
- `msg_id` is a UUID; timestamps are ISO-8601 UTC.
- Rendezvous calls must respect a 50 req/min rate limit.

## Logging

Configured once in `main.py` as `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
Each module uses a named logger (e.g. `logging.getLogger("Router")`,
`"KeepAlive"`, `"PeerConn"`) so the `[Module]` tag identifies the source.
Observability is graded — keep log lines in the spec's style (e.g.
`Sent N PINGs | Average RTT = X ms`). The `/log <LEVEL>` CLI command adjusts the
level at runtime.
