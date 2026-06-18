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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from p2p_client import P2PClient

LOG = logging.getLogger("CLI")

_HELP = """\
Comandos disponíveis:
  /peers [* | #namespace]       descobrir e listar peers
  /msg <peer_id> <mensagem>     mensagem direta (SEND)
  /pub * <mensagem>             broadcast global
  /pub #<namespace> <mensagem>  mensagem para um namespace
  /conn                         conexões ativas (inbound/outbound)
  /rtt                          RTT médio por peer
  /reconnect                    forçar reconciliação de peers
  /log <Nível>                  ajustar nível de log (DEBUG, INFO, ...)
  /help                         mostrar esta ajuda
  /quit                         encerrar (BYE + UNREGISTER)"""


class CLI:
    """Loop de leitura de comandos do usuário."""

    def __init__(self, client: "P2PClient") -> None:
        self.client = client
        self._running = False

    def run(self) -> None:
        """Loop principal: lê linhas do stdin e despacha comandos."""
        self._running = True
        print(_HELP)
        while self._running:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            if not line:
                continue
            try:
                self.dispatch(line)
            except Exception as exc:  # noqa: BLE001 — a CLI não deve cair
                LOG.error("Erro ao executar comando: %s", exc)
        self._running = False

    def dispatch(self, line: str) -> None:
        """Interpreta uma linha de comando e chama o handler correspondente."""
        if not line.startswith("/"):
            print("Comandos começam com '/'. Use /help.")
            return
        head, _, rest = line.partition(" ")
        cmd = head[1:].lower()
        rest = rest.strip()

        if cmd == "peers":
            self.cmd_peers(rest or None)
        elif cmd == "msg":
            peer_id, _, message = rest.partition(" ")
            if not peer_id or not message.strip():
                print("Uso: /msg <peer_id> <mensagem>")
                return
            self.cmd_msg(peer_id, message.strip())
        elif cmd == "pub":
            scope, _, message = rest.partition(" ")
            if not scope or not message.strip():
                print("Uso: /pub <* | #namespace> <mensagem>")
                return
            self.cmd_pub(scope, message.strip())
        elif cmd == "conn":
            self.cmd_conn()
        elif cmd == "rtt":
            self.cmd_rtt()
        elif cmd == "reconnect":
            self.cmd_reconnect()
        elif cmd == "log":
            if not rest:
                print("Uso: /log <DEBUG|INFO|WARNING|ERROR>")
                return
            self.cmd_log(rest)
        elif cmd in ("quit", "exit"):
            self.cmd_quit()
        elif cmd == "help":
            print(_HELP)
        else:
            print(f"Comando desconhecido: /{cmd} (use /help)")

    # -- handlers de comando ---------------------------------------------

    def cmd_peers(self, arg: str | None) -> None:
        """/peers — descobre e lista peers (opcional filtro * ou #namespace)."""
        if not arg:
            namespace = self.client.namespace
        elif arg == "*":
            namespace = None  # todos os namespaces
        elif arg.startswith("#"):
            namespace = arg[1:]
        else:
            namespace = arg
        peers = self.client.discover_now(namespace)
        if not peers:
            print("Nenhum peer encontrado.")
            return
        print(f"{len(peers)} peer(s):")
        for p in peers:
            print(
                f"  {p.get('name')}@{p.get('namespace')}"
                f"  {p.get('ip')}:{p.get('port')}"
                f"  (expira em {p.get('expires_in', '?')}s)"
            )

    def cmd_msg(self, peer_id: str, message: str) -> None:
        """/msg — envia mensagem direta (SEND) a um peer_id."""
        msg_id = self.client.router.send(peer_id, message)
        if msg_id is None:
            print(f"Não foi possível enviar para {peer_id} (não conectado).")

    def cmd_pub(self, scope: str, message: str) -> None:
        """/pub — publica para namespace (#ns) ou broadcast (*)."""
        self.client.router.pub(scope, message)

    def cmd_conn(self) -> None:
        """/conn — lista conexões ativas (inbound/outbound)."""
        conns = self.client.peer_table.active_connections()
        if not conns:
            print("Nenhuma conexão ativa.")
            return
        print(f"{len(conns)} conexão(ões) ativa(s):")
        for c in conns:
            print(f"  {c.peer_id}  [{c.direction.value}]")

    def cmd_rtt(self) -> None:
        """/rtt — exibe RTT médio por peer."""
        shown = False
        for entry in self.client.peer_table.all():
            rtt = self.client.keep_alive.average_rtt(entry.peer_id)
            if rtt is not None:
                print(f"  {entry.peer_id}: {rtt:.1f} ms")
                shown = True
        if not shown:
            print("Nenhum RTT registrado ainda.")

    def cmd_reconnect(self) -> None:
        """/reconnect — força reconciliação/reconexão de peers."""
        self.client.reconnect()
        print("Reconciliação disparada.")

    def cmd_log(self, level: str) -> None:
        """/log — ajusta o nível de log em tempo de execução."""
        lvl = getattr(logging, level.upper(), None)
        if not isinstance(lvl, int):
            print(f"Nível inválido: {level}")
            return
        logging.getLogger().setLevel(lvl)
        print(f"Nível de log ajustado para {level.upper()}.")

    def cmd_quit(self) -> None:
        """/quit — encerra a aplicação (BYE + UNREGISTER)."""
        print("Encerrando...")
        self._running = False
