"""cli.py — Interface de linha de comando (Critério 6).

Lê comandos do usuário em loop e os traduz em chamadas ao P2PClient.

Comandos:
  /peers [* | #namespace]      descobrir e listar peers
  /msg <peer_id> <mensagem>    mensagem direta (SEND)
  /pub * <mensagem>            broadcast global
  /pub #<namespace> <mensagem> mensagem para um namespace
  /conn                        conexões ativas (inbound/outbound)
  /rtt                         RTT médio por peer
  /reconnect                   forçar reconciliação de peers
  /log <Nível>                 ajustar nível de log
  /quit                        encerrar (BYE + UNREGISTER)
"""

from __future__ import annotations

import logging
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from p2p_client import P2PClient

LOG = logging.getLogger("CLI")


class CLI:
    """Loop de leitura de comandos do usuário."""

    def __init__(self, client: "P2PClient") -> None:
        self.client = client
        self._running = False

    def run(self) -> None:
        """Loop principal: lê linhas do stdin e despacha comandos.

        TODO: while running: input(), parse, dispatch; tratar EOF/KeyboardInterrupt.
        """
        raise NotImplementedError

    def dispatch(self, line: str) -> None:
        """Interpreta uma linha de comando e chama o handler correspondente.

        TODO: separar comando e argumentos, rotear para cmd_*.
        """
        raise NotImplementedError

    # -- handlers de comando ---------------------------------------------

    def cmd_peers(self, arg: str | None) -> None:
        """/peers — descobre e lista peers (opcional filtro * ou #namespace)."""
        raise NotImplementedError

    def cmd_msg(self, peer_id: str, message: str) -> None:
        """/msg — envia mensagem direta (SEND) a um peer_id."""
        raise NotImplementedError

    def cmd_pub(self, scope: str, message: str) -> None:
        """/pub — publica para namespace (#ns) ou broadcast (*)."""
        raise NotImplementedError

    def cmd_conn(self) -> None:
        """/conn — lista conexões ativas (inbound/outbound)."""
        raise NotImplementedError

    def cmd_rtt(self) -> None:
        """/rtt — exibe RTT médio por peer."""
        raise NotImplementedError

    def cmd_reconnect(self) -> None:
        """/reconnect — força reconciliação/reconexão de peers."""
        raise NotImplementedError

    def cmd_log(self, level: str) -> None:
        """/log — ajusta o nível de log em tempo de execução."""
        raise NotImplementedError

    def cmd_quit(self) -> None:
        """/quit — encerra a aplicação (BYE + UNREGISTER)."""
        raise NotImplementedError
