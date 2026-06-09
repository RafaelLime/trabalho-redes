"""peer_table.py — Tabela de peers, estados e reconexão (Critério 5).

Mantém o estado de cada peer conhecido (descoberto ou conectado), diferencia
peers novos dos já conhecidos a cada DISCOVER, controla dedupe de conexões e
guarda a política de reconexão com backoff exponencial.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from state import PeerState

if TYPE_CHECKING:
    from peer_connection import PeerConnection

LOG = logging.getLogger("PeerTable")


@dataclass
class PeerEntry:
    """Registro de um peer conhecido.

    Attributes:
        peer_id       : name@namespace.
        ip, port      : endereço de escuta do peer (do DISCOVER).
        namespace     : namespace do peer.
        state         : estado atual (ver PeerState).
        conn          : conexão ativa associada, se houver.
        reconnect_attempts : tentativas de reconexão já feitas.
        next_backoff  : próximo atraso de backoff (segundos).
    """

    peer_id: str
    ip: str
    port: int
    namespace: str
    state: PeerState = PeerState.KNOWN
    conn: Optional["PeerConnection"] = None
    reconnect_attempts: int = 0
    next_backoff: float = 1.0


class PeerTable:
    """Coleção thread-safe de PeerEntry indexada por peer_id."""

    def __init__(self, local_peer_id: str, max_reconnect_attempts: int) -> None:
        self.local_peer_id = local_peer_id
        self.max_reconnect_attempts = max_reconnect_attempts
        self._peers: dict[str, PeerEntry] = {}
        self._lock = threading.Lock()

    # -- descoberta -------------------------------------------------------

    def merge_discovered(self, peers: list[dict]) -> list[PeerEntry]:
        """Mescla resultado de um DISCOVER; retorna apenas os peers NOVOS.

        Diferencia conhecidos de novos (rubrica) e ignora o próprio peer.

        TODO: criar PeerEntry para peers inéditos, atualizar existentes.
        """
        raise NotImplementedError

    # -- dedupe / estado --------------------------------------------------

    def should_dial(self, peer_id: str) -> bool:
        """Decide se devemos discar a este peer (dedupe).

        Não disca se já há conexão (inbound ou outbound) ou se ele já
        se conectou a nós. Regra de desempate sugerida: comparar peer_ids.

        TODO: implementar regra de dedupe por peer_id.
        """
        raise NotImplementedError

    def set_state(self, peer_id: str, state: PeerState) -> None:
        """Atualiza o estado de um peer.

        TODO: atualizar PeerEntry.state sob lock.
        """
        raise NotImplementedError

    def attach_conn(self, peer_id: str, conn: "PeerConnection") -> None:
        """Associa uma conexão ativa a um peer e zera o backoff.

        TODO: setar entry.conn, state=ACTIVE, reset reconnect_attempts.
        """
        raise NotImplementedError

    def mark_stale(self, peer_id: str) -> None:
        """Marca um peer como STALE (não respondeu a PING).

        TODO: set_state(STALE) e disparar lógica de reconexão.
        """
        raise NotImplementedError

    # -- reconexão --------------------------------------------------------

    def next_reconnect_delay(self, peer_id: str) -> Optional[float]:
        """Calcula o próximo atraso de backoff; None se excedeu o limite.

        TODO: backoff exponencial até max_reconnect_attempts.
        """
        raise NotImplementedError

    # -- consultas --------------------------------------------------------

    def active_connections(self) -> list["PeerConnection"]:
        """Lista as conexões atualmente ACTIVE.

        TODO: filtrar entries com conn e state ACTIVE.
        """
        raise NotImplementedError

    def peers_in_namespace(self, namespace: str) -> list[PeerEntry]:
        """Peers ativos pertencentes a um namespace (para PUB #ns).

        TODO: filtrar por namespace e estado.
        """
        raise NotImplementedError

    def get(self, peer_id: str) -> Optional[PeerEntry]:
        """Retorna o PeerEntry de um peer_id, se existir."""
        with self._lock:
            return self._peers.get(peer_id)

    def all(self) -> list[PeerEntry]:
        """Retorna uma cópia de todos os PeerEntry."""
        with self._lock:
            return list(self._peers.values())
