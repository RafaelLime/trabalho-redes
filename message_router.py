"""message_router.py — Envio e publicação de mensagens (Critério 3).

Responsável por:
  - SEND unicast com require_ack=true e timeout de ACK (5 s).
  - ACK em resposta a SEND endereçado a este peer.
  - PUB namespace-cast (`#ns`) e broadcast (`*`).
  - Dispatch das mensagens recebidas conforme `type`.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Optional

from state import MsgType, P2P_TTL, new_msg_id, utc_timestamp

if TYPE_CHECKING:
    from peer_connection import PeerConnection
    from peer_table import PeerTable

LOG = logging.getLogger("Router")


class MessageRouter:
    """Roteia mensagens de aplicação (SEND/ACK/PUB) entre peers.

    Attributes:
        local_peer_id : identidade deste peer.
        peer_table    : tabela para localizar conexões por peer_id/namespace.
        ack_timeout   : segundos a aguardar por ACK antes de logar timeout.
    """

    def __init__(self, local_peer_id: str, peer_table: "PeerTable", ack_timeout: int) -> None:
        self.local_peer_id = local_peer_id
        self.peer_table = peer_table
        self.ack_timeout = ack_timeout
        # msg_id -> timer de timeout aguardando ACK.
        self._pending_acks: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    # -- envio ------------------------------------------------------------

    def send(self, dst: str, payload: str) -> Optional[str]:
        """Envia SEND unicast a `dst` com require_ack=true.

        Retorna o msg_id gerado, ou None se o peer não estiver conectado.
        Agenda um timer de timeout de ACK.
        """
        entry = self.peer_table.get(dst)
        if entry is None or entry.conn is None:
            LOG.warning("SEND falhou: %s não está conectado", dst)
            return None
        msg_id = new_msg_id()
        msg = {
            "type": MsgType.SEND.value,
            "msg_id": msg_id,
            "src": self.local_peer_id,
            "dst": dst,
            "payload": payload,
            "require_ack": True,
            "ttl": P2P_TTL,
        }
        try:
            entry.conn.send(msg)
        except OSError as exc:
            LOG.warning("SEND falhou para %s: %s", dst, exc)
            return None
        timer = threading.Timer(self.ack_timeout, self._on_ack_timeout, args=(msg_id, dst))
        timer.daemon = True
        with self._lock:
            self._pending_acks[msg_id] = timer
        timer.start()
        LOG.info("SEND %s: %s", dst, payload)
        return msg_id

    def pub(self, dst: str, payload: str) -> Optional[str]:
        """Publica PUB para namespace (`#ns`) ou broadcast (`*`)."""
        if dst == "*":
            targets = self.peer_table.active_connections()
        elif dst.startswith("#"):
            namespace = dst[1:]
            targets = [e.conn for e in self.peer_table.peers_in_namespace(namespace)]
        else:
            LOG.warning("PUB: destino inválido %r (use '*' ou '#namespace')", dst)
            return None
        msg_id = new_msg_id()
        msg = {
            "type": MsgType.PUB.value,
            "msg_id": msg_id,
            "src": self.local_peer_id,
            "dst": dst,
            "payload": payload,
            "require_ack": False,
            "ttl": P2P_TTL,
        }
        count = 0
        for conn in targets:
            if conn is None:
                continue
            try:
                conn.send(msg)
                count += 1
            except OSError:
                pass
        LOG.info("PUB %s para %d peer(s): %s", dst, count, payload)
        return msg_id

    # -- recepção ---------------------------------------------------------

    def on_send(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Trata SEND recebido: entrega o payload e responde ACK se pedido."""
        src = msg.get("src", "?")
        payload = msg.get("payload", "")
        print(f"\n[{src}] {payload}")
        LOG.info("SEND recebido de %s: %s", src, payload)
        if msg.get("require_ack"):
            ack = {
                "type": MsgType.ACK.value,
                "msg_id": msg.get("msg_id"),
                "timestamp": utc_timestamp(),
                "ttl": P2P_TTL,
            }
            try:
                conn.send(ack)
            except OSError:
                pass

    def on_ack(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Casa ACK por msg_id e cancela o timer de timeout."""
        msg_id = msg.get("msg_id")
        with self._lock:
            timer = self._pending_acks.pop(msg_id, None)
        if timer is not None:
            timer.cancel()
            LOG.info("ACK recebido para msg_id=%s", msg_id)

    def on_pub(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Trata PUB recebido: entrega o payload ao usuário."""
        src = msg.get("src", "?")
        dst = msg.get("dst", "?")
        payload = msg.get("payload", "")
        print(f"\n[{src} -> {dst}] {payload}")
        LOG.info("PUB recebido de %s (%s): %s", src, dst, payload)

    def _on_ack_timeout(self, msg_id: str, dst: str) -> None:
        """Callback do timer: loga aviso de ACK não recebido em ack_timeout s."""
        with self._lock:
            self._pending_acks.pop(msg_id, None)
        LOG.warning("ACK timeout para msg_id=%s (dst=%s)", msg_id, dst)
