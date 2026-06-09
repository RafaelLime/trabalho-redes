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
from typing import TYPE_CHECKING, Any

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

    def send(self, dst: str, payload: str) -> str:
        """Envia SEND unicast a `dst` com require_ack=true.

        Retorna o msg_id gerado. Agenda timeout de ACK.

        TODO: localizar conexão de dst, montar SEND, enviar, armar timer.
        """
        raise NotImplementedError

    def pub(self, dst: str, payload: str) -> str:
        """Publica PUB para namespace (`#ns`) ou broadcast (`*`).

        TODO: selecionar peers-alvo conforme dst, montar PUB e enviar a todos.
        """
        raise NotImplementedError

    # -- recepção ---------------------------------------------------------

    def on_send(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Trata SEND recebido: entrega o payload e responde ACK se pedido.

        TODO: exibir mensagem, se require_ack enviar ACK com mesmo msg_id.
        """
        raise NotImplementedError

    def on_ack(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Casa ACK por msg_id e cancela o timer de timeout.

        TODO: cancelar self._pending_acks[msg_id].
        """
        raise NotImplementedError

    def on_pub(self, conn: "PeerConnection", msg: dict[str, Any]) -> None:
        """Trata PUB recebido: entrega o payload ao usuário.

        TODO: exibir mensagem de namespace/broadcast.
        """
        raise NotImplementedError

    def _on_ack_timeout(self, msg_id: str, dst: str) -> None:
        """Callback do timer: loga aviso de ACK não recebido em ack_timeout s."""
        LOG.warning("ACK timeout para msg_id=%s (dst=%s)", msg_id, dst)
