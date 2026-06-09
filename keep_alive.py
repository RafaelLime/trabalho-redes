"""keep_alive.py — Keep-alive PING/PONG e métricas de RTT (Critérios 2 e 3).

Uma thread envia PING a cada `ping_interval` segundos para cada conexão ativa.
PONGs são casados por `msg_id` para calcular o RTT. Peers que não respondem
são marcados como STALE.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from peer_connection import PeerConnection
    from peer_table import PeerTable

LOG = logging.getLogger("KeepAlive")


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
        """Inicia a thread periódica de PING.

        TODO: criar self._thread em loop até self._stop.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Sinaliza parada da thread de keep-alive."""
        self._stop.set()

    def _ping_loop(self) -> None:
        """A cada ping_interval, envia PING para cada conexão ativa.

        TODO: iterar conexões ativas, send_ping, checar pendências vencidas.
        """
        raise NotImplementedError

    def send_ping(self, conn: "PeerConnection") -> None:
        """Envia um PING (msg_id + timestamp) e registra a pendência.

        TODO: montar PING, guardar em self._pending, conn.send.
        """
        raise NotImplementedError

    def on_ping(self, conn: "PeerConnection", msg: dict) -> None:
        """Responde PONG ao receber PING (mesmo msg_id).

        TODO: montar PONG com msg_id recebido e enviar.
        """
        raise NotImplementedError

    def on_pong(self, conn: "PeerConnection", msg: dict) -> None:
        """Casa PONG por msg_id, calcula RTT e atualiza estatísticas.

        TODO: remover de self._pending, calcular RTT, registrar.
        """
        raise NotImplementedError

    def average_rtt(self, peer_id: str) -> float | None:
        """Retorna o RTT médio (ms) registrado para um peer, se houver.

        TODO: média de self._rtts[peer_id].
        """
        raise NotImplementedError
