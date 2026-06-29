"""peer_table.py — Tabela de peers, estados e reconexão (Critério 5).

Mantém o estado de cada peer conhecido (descoberto ou conectado), diferencia
peers novos dos já conhecidos a cada DISCOVER, controla dedupe de conexões e
guarda a política de reconexão com backoff exponencial.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from state import PeerState, make_peer_id, split_peer_id

if TYPE_CHECKING:
    from peer_connection import PeerConnection

LOG = logging.getLogger("PeerTable")

# Limite superior do backoff exponencial (segundos).
_MAX_BACKOFF = 60.0


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
        Peers já conhecidos têm ip/port atualizados sem alterar o estado.
        """
        new_entries: list[PeerEntry] = []
        with self._lock:
            for p in peers:
                name = p.get("name")
                namespace = p.get("namespace")
                ip = p.get("ip")
                port = p.get("port")
                if name is None or namespace is None or ip is None or port is None:
                    LOG.debug("Peer descoberto incompleto, ignorando: %r", p)
                    continue
                peer_id = make_peer_id(name, namespace)
                if peer_id == self.local_peer_id:
                    continue  # ignora a si mesmo
                existing = self._peers.get(peer_id)
                if existing is None:
                    entry = PeerEntry(
                        peer_id=peer_id, ip=ip, port=port, namespace=namespace
                    )
                    self._peers[peer_id] = entry
                    new_entries.append(entry)
                    LOG.info("Novo peer descoberto: %s (%s:%s)", peer_id, ip, port)
                else:
                    # Peer já conhecido: atualiza endereço se mudou.
                    existing.ip = ip
                    existing.port = port
        return new_entries

    # -- dedupe / estado --------------------------------------------------

    def should_dial(self, peer_id: str) -> bool:
        """Decide se devemos discar a este peer (dedupe).

        Não disca se já há conexão ou se uma tentativa está em andamento.
        Para evitar que ambos os lados se conectem simultaneamente, apenas o
        peer de menor `peer_id` inicia a conexão; o outro aguarda o inbound.
        """
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is None:
                return False
            if entry.conn is not None:
                return False
            if entry.state in (PeerState.CONNECTING, PeerState.ACTIVE):
                return False
            # Desempate determinístico: o menor peer_id é quem disca.
            if self.local_peer_id > peer_id:
                return False
            return True

    def set_state(self, peer_id: str, state: PeerState) -> None:
        """Atualiza o estado de um peer."""
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is not None:
                entry.state = state

    def attach_conn(self, peer_id: str, conn: "PeerConnection") -> None:
        """Associa uma conexão ativa a um peer e zera o backoff.

        Cria um PeerEntry mínimo se o peer ainda não era conhecido (caso de
        uma conexão inbound de um peer que ainda não descobrimos).
        """
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is None:
                _, namespace = split_peer_id(peer_id)
                entry = PeerEntry(peer_id=peer_id, ip="", port=0, namespace=namespace)
                self._peers[peer_id] = entry
            entry.conn = conn
            entry.state = PeerState.ACTIVE
            entry.reconnect_attempts = 0
            entry.next_backoff = 1.0

    def clear_conn(self, peer_id: str, conn: "PeerConnection") -> None:
        """Remove a conexão de um peer, se for exatamente `conn`."""
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is not None and entry.conn is conn:
                entry.conn = None

    def mark_stale(self, peer_id: str) -> None:
        """Marca um peer como STALE (não respondeu a PING)."""
        self.set_state(peer_id, PeerState.STALE)

    # -- reconexão --------------------------------------------------------

    def next_reconnect_delay(self, peer_id: str) -> Optional[float]:
        """Calcula o próximo atraso de backoff; None se excedeu o limite.

        Aplica backoff exponencial (1s, 2s, 4s, ...) até `_MAX_BACKOFF`,
        limitado a `max_reconnect_attempts` tentativas.
        """
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is None:
                return None
            if entry.reconnect_attempts >= self.max_reconnect_attempts:
                entry.state = PeerState.FAILED
                return None
            delay = entry.next_backoff
            entry.reconnect_attempts += 1
            entry.next_backoff = min(entry.next_backoff * 2, _MAX_BACKOFF)
            return delay

    def reset_reconnect(self, peer_id: str) -> None:
        """Zera o contador/backoff de reconexão (ex.: /reconnect manual)."""
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry is not None:
                entry.reconnect_attempts = 0
                entry.next_backoff = 1.0

    # -- consultas --------------------------------------------------------

    def active_connections(self) -> list["PeerConnection"]:
        """Lista as conexões atualmente ACTIVE."""
        with self._lock:
            return [
                e.conn
                for e in self._peers.values()
                if e.conn is not None and e.state == PeerState.ACTIVE
            ]

    def peers_in_namespace(self, namespace: str) -> list[PeerEntry]:
        """Peers ativos pertencentes a um namespace (para PUB #ns)."""
        with self._lock:
            return [
                e
                for e in self._peers.values()
                if e.namespace == namespace
                and e.state == PeerState.ACTIVE
                and e.conn is not None
            ]

    def get(self, peer_id: str) -> Optional[PeerEntry]:
        """Retorna o PeerEntry de um peer_id, se existir."""
        with self._lock:
            return self._peers.get(peer_id)

    def all(self) -> list[PeerEntry]:
        """Retorna uma cópia de todos os PeerEntry."""
        with self._lock:
            return list(self._peers.values())
