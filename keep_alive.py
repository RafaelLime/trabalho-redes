"""keep_alive.py — Keep-alive PING/PONG e métricas de RTT (Critérios 2 e 3).

Uma thread envia PING a cada `ping_interval` segundos para cada conexão ativa.
PONGs são casados por `msg_id` para calcular o RTT. Peers que não respondem
são marcados como STALE.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from state import MsgType, P2P_TTL, new_msg_id, utc_timestamp

if TYPE_CHECKING:
    from peer_connection import PeerConnection
    from peer_table import PeerTable

LOG = logging.getLogger("KeepAlive")

# Quantos RTTs recentes guardar por peer para a média.
_RTT_HISTORY = 20


class KeepAlive:
    """Gerencia o ciclo PING/PONG e estatísticas de RTT.

    Attributes:
        ping_interval : intervalo entre PINGs (segundos).
        peer_table    : tabela de peers para marcar STALE.
    """

    def __init__(self, ping_interval: int, peer_table: "PeerTable") -> None:
        self.ping_interval = ping_interval
        self.peer_table = peer_table
        # msg_id -> (peer_id, timestamp_envio) para casar PONG e medir RTT.
        self._pending: dict[str, tuple[str, float]] = {}
        self._rtts: dict[str, list[float]] = {}
        self._ping_count = 0
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        """Inicia a thread periódica de PING."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._ping_loop, name="keepalive", daemon=True
        )
        self._thread.start()
        LOG.info("Keep-alive iniciado (PING a cada %ds)", self.ping_interval)

    def stop(self) -> None:
        """Sinaliza parada da thread de keep-alive."""
        self._stop.set()

    def _ping_loop(self) -> None:
        """A cada ping_interval, envia PING para cada conexão ativa."""
        while not self._stop.wait(self.ping_interval):
            conns = self.peer_table.active_connections()
            sent = 0
            for conn in conns:
                try:
                    self.send_ping(conn)
                    sent += 1
                except OSError:
                    pass  # conexão morrendo; o reader/close trata
            self._check_timeouts()
            if sent:
                avg = self._overall_avg_rtt()
                if avg is not None:
                    LOG.info("Sent %d PINGs | Average RTT = %.1f ms", sent, avg)
                else:
                    LOG.info("Sent %d PINGs | Average RTT = n/a", sent)

    def send_ping(self, conn: "PeerConnection") -> None:
        """Envia um PING (msg_id + timestamp) e registra a pendência."""
        if conn.peer_id is None:
            return
        msg_id = new_msg_id()
        msg = {
            "type": MsgType.PING.value,
            "msg_id": msg_id,
            "timestamp": utc_timestamp(),
            "ttl": P2P_TTL,
        }
        with self._lock:
            self._pending[msg_id] = (conn.peer_id, time.monotonic())
            self._ping_count += 1
        conn.send(msg)

    def on_ping(self, conn: "PeerConnection", msg: dict) -> None:
        """Responde PONG ao receber PING (mesmo msg_id)."""
        pong = {
            "type": MsgType.PONG.value,
            "msg_id": msg.get("msg_id"),
            "timestamp": utc_timestamp(),
            "ttl": P2P_TTL,
        }
        try:
            conn.send(pong)
        except OSError:
            pass

    def on_pong(self, conn: "PeerConnection", msg: dict) -> None:
        """Casa PONG por msg_id, calcula RTT e atualiza estatísticas."""
        msg_id = msg.get("msg_id")
        with self._lock:
            pending = self._pending.pop(msg_id, None)
        if pending is None:
            return  # PONG desconhecido ou já expirado
        peer_id, sent_at = pending
        rtt = (time.monotonic() - sent_at) * 1000.0  # ms
        with self._lock:
            history = self._rtts.setdefault(peer_id, [])
            history.append(rtt)
            del history[:-_RTT_HISTORY]
        LOG.debug("PONG de %s | RTT = %.1f ms", peer_id, rtt)

    def _check_timeouts(self) -> None:
        """Pendências antigas (> 2x ping_interval) marcam o peer como STALE."""
        now = time.monotonic()
        threshold = self.ping_interval * 2
        stale_peers: set[str] = set()
        with self._lock:
            expired = [
                (mid, pid)
                for mid, (pid, sent_at) in self._pending.items()
                if now - sent_at > threshold
            ]
            for mid, pid in expired:
                self._pending.pop(mid, None)
                stale_peers.add(pid)
        for pid in stale_peers:
            LOG.warning("Peer %s não respondeu PING; marcando STALE", pid)
            self.peer_table.mark_stale(pid)

    def average_rtt(self, peer_id: str) -> float | None:
        """Retorna o RTT médio (ms) registrado para um peer, se houver."""
        with self._lock:
            rtts = self._rtts.get(peer_id)
            if not rtts:
                return None
            return sum(rtts) / len(rtts)

    def _overall_avg_rtt(self) -> float | None:
        """RTT médio (ms) considerando todos os peers, se houver amostras."""
        with self._lock:
            samples = [r for lst in self._rtts.values() for r in lst]
        if not samples:
            return None
        return sum(samples) / len(samples)
