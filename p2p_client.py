"""p2p_client.py — Lógica principal do cliente P2P.

Orquestra todos os módulos:
  - registro inicial e renovação de TTL no Rendezvous;
  - DISCOVER periódico e conexão automática a peers novos;
  - servidor de escuta + dialer com dedupe;
  - keep-alive, roteamento de mensagens e reconexão;
  - encerramento limpo (BYE + UNREGISTER + shutdown).
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Optional

from keep_alive import KeepAlive
from message_router import MessageRouter
from peer_connection import Direction, PeerConnection, PeerServer
from peer_table import PeerEntry, PeerTable
from rendezvous_connection import RendezvousConnection
from state import MsgType, P2P_TTL, PeerState, make_peer_id, new_msg_id

LOG = logging.getLogger("Client")

# Tempo máximo (s) para estabelecer a conexão TCP outbound.
_CONNECT_TIMEOUT = 10.0
# Tempo máximo (s) aguardando o HELLO numa conexão inbound.
_HANDSHAKE_TIMEOUT = 10.0


class P2PClient:
    """Cliente de chat P2P de alto nível.

    Reúne configuração e instancia os subsistemas. Os métodos de ciclo de
    vida (start/run/stop) e os callbacks de mensagem são o coração da
    orquestração.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name: str = config["name"]
        self.namespace: str = config["namespace"]
        self.listen_port: int = config["listen_port"]
        self.ttl: int = config.get("ttl", 3600)
        self.peer_id = make_peer_id(self.name, self.namespace)

        # Subsistemas (instanciados aqui; ligados em start()).
        self.rendezvous = RendezvousConnection(
            config["rendezvous_host"], config["rendezvous_port"]
        )
        self.peer_table = PeerTable(self.peer_id, config["max_reconnect_attempts"])
        self.router = MessageRouter(self.peer_id, self.peer_table, config["ack_timeout"])
        self.keep_alive = KeepAlive(config["ping_interval"], self.peer_table)
        self.server = PeerServer(self.listen_port, self.peer_id, self._on_accept)

        self._discover_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- ciclo de vida ----------------------------------------------------

    def start(self) -> None:
        """Sobe servidor, registra no Rendezvous e inicia threads de fundo."""
        self._stop.clear()
        self.server.start()
        self.rendezvous.register(self.namespace, self.name, self.listen_port, self.ttl)
        self.rendezvous.start_renew(self.namespace, self.name, self.listen_port, self.ttl)
        self.keep_alive.start()
        self._discover_thread = threading.Thread(
            target=self._discover_loop, name="discover", daemon=True
        )
        self._discover_thread.start()
        # Descoberta inicial imediata (não espera o primeiro intervalo).
        self.discover_now(self.namespace)
        LOG.info("Cliente %s iniciado", self.peer_id)

    def stop(self) -> None:
        """Encerramento limpo: BYE em todas as conexões + UNREGISTER + shutdown."""
        if self._stop.is_set():
            return
        self._stop.set()
        LOG.info("Encerrando cliente %s...", self.peer_id)

        # BYE em todas as conexões ativas.
        for conn in self.peer_table.active_connections():
            try:
                bye = {
                    "type": MsgType.BYE.value,
                    "msg_id": new_msg_id(),
                    "src": self.peer_id,
                    "dst": conn.peer_id,
                    "reason": "shutdown",
                    "ttl": P2P_TTL,
                }
                conn.send(bye)
            except OSError:
                pass

        # Para threads de fundo.
        self.keep_alive.stop()
        self.rendezvous.stop_renew()

        # Remove o registro no Rendezvous.
        try:
            self.rendezvous.unregister(self.namespace, self.name, self.listen_port)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Falha no UNREGISTER: %s", exc)

        # Fecha sockets.
        self.server.stop()
        for conn in self.peer_table.active_connections():
            conn.close("shutdown")
        LOG.info("Cliente %s encerrado", self.peer_id)

    # -- descoberta e conexão --------------------------------------------

    def _discover_loop(self) -> None:
        """Thread: DISCOVER periódico e conexão a peers novos."""
        interval = self.config["discover_interval"]
        while not self._stop.wait(interval):
            try:
                self.discover_now(self.namespace)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Erro no discover periódico: %s", exc)

    def discover_now(self, namespace: Optional[str] = None) -> list:
        """Executa um DISCOVER imediato e reconcilia a PeerTable.

        Retorna a lista bruta de peers (para a CLI exibir).
        """
        peers = self.rendezvous.discover(namespace)
        new_entries = self.peer_table.merge_discovered(peers)
        LOG.info("Executando discover...")

        def dial_new_peers() -> None:

            for entry in new_entries:
                self.connect_to(entry)
        
        if new_entries:
            t = threading.Thread(target=dial_new_peers, name="dialer", daemon=True)
            t.start()
        
        return peers

    def connect_to(self, entry: PeerEntry) -> None:
        """Disca a um peer (outbound) e executa o handshake HELLO."""
        LOG.info("Iniciando conexão com %s...", entry.peer_id)
        if not self.peer_table.should_dial(entry.peer_id):
            LOG.info("Dedupe: não discando para %s", entry.peer_id)
            return
        self.peer_table.set_state(entry.peer_id, PeerState.CONNECTING)
        LOG.info("State: CONNECTING")
        dial_ip = self._dial_host(entry.ip)
        LOG.info("Conectando a %s (%s:%d)...", entry.peer_id, dial_ip, entry.port)
        try:
            sock = socket.create_connection(
                (dial_ip, entry.port), timeout=_CONNECT_TIMEOUT
            )
        except OSError as exc:
            LOG.warning("Falha ao conectar a %s: %s", entry.peer_id, exc)
            self.peer_table.set_state(entry.peer_id, PeerState.STALE)
            self._schedule_reconnect(entry.peer_id)
            return

        conn = PeerConnection(
            sock, Direction.OUTBOUND, self.peer_id, self._on_message, self._on_conn_close
        )
        if not conn.do_handshake_outbound():
            LOG.warning("Handshake falhou com %s", entry.peer_id)
            conn.close("handshake failed")
            self.peer_table.set_state(entry.peer_id, PeerState.STALE)
            self._schedule_reconnect(entry.peer_id)
            return

        self.peer_table.attach_conn(entry.peer_id, conn)
        conn.start_reader()
        LOG.info("Conectado a %s", entry.peer_id)

    def _dial_host(self, peer_ip: str) -> str:
        """Resolve o host de discagem, tratando o caso NAT/loopback.

        O Rendezvous anuncia o IP público de cada peer. Se o IP de um peer for
        igual ao nosso próprio IP público, ele está atrás do mesmo NAT (ex.:
        dois peers na mesma máquina/rede em teste), então discamos para
        127.0.0.1, que é alcançável localmente.
        """
        if peer_ip and peer_ip == self.rendezvous.public_ip:
            return "127.0.0.1"
        return peer_ip

    def reconnect(self) -> None:
        """Força reconciliação/reconexão de peers STALE/FAILED (CLI /reconnect)."""
        LOG.info("Reconciliação forçada de peers...")
        try:
            self.discover_now(self.namespace)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Erro no DISCOVER durante /reconnect: %s", exc)
        for entry in self.peer_table.all():
            if entry.conn is None and entry.state in (
                PeerState.STALE, PeerState.FAILED, PeerState.KNOWN
            ):
                self.peer_table.reset_reconnect(entry.peer_id)
                self.peer_table.set_state(entry.peer_id, PeerState.KNOWN)
                self.connect_to(entry)

    def _schedule_reconnect(self, peer_id: str) -> None:
        """Agenda uma reconexão com backoff exponencial, se ainda permitido."""
        if self._stop.is_set():
            return
        delay = self.peer_table.next_reconnect_delay(peer_id)
        if delay is None:
            LOG.warning("Peer %s excedeu tentativas de reconexão (FAILED)", peer_id)
            return
        LOG.info("Reagendando conexão com %s em %.1fs", peer_id, delay)
        timer = threading.Timer(delay, self._reconnect_peer, args=(peer_id,))
        timer.daemon = True
        timer.start()

    def _reconnect_peer(self, peer_id: str) -> None:
        """Callback do timer de backoff: tenta reconectar a um peer."""
        if self._stop.is_set():
            return
        entry = self.peer_table.get(peer_id)
        if entry is None or entry.conn is not None:
            return
        if entry.state == PeerState.ACTIVE:
            return
        self.peer_table.set_state(peer_id, PeerState.KNOWN)
        self.connect_to(entry)

    # -- conexões inbound -------------------------------------------------

    def _on_accept(self, sock: socket.socket, addr: tuple) -> None:
        """Callback do PeerServer para cada conexão inbound aceita."""
        conn = PeerConnection(
            sock, Direction.INBOUND, self.peer_id, self._on_message, self._on_conn_close
        )
        hello = conn.recv_hello(timeout=_HANDSHAKE_TIMEOUT)
        if hello is None or hello.get("type") != MsgType.HELLO.value:
            LOG.warning("Inbound de %s sem HELLO válido; fechando", addr)
            conn.close("no hello")
            return
        conn.handle_hello_inbound(hello)
        if conn.peer_id is None:
            LOG.warning("HELLO inbound sem peer_id; fechando")
            conn.close("bad hello")
            return
        self.peer_table.attach_conn(conn.peer_id, conn)
        conn.start_reader()
        LOG.info("Conexão inbound estabelecida com %s", conn.peer_id)

    # -- dispatch de mensagens -------------------------------------------

    def _on_message(self, conn: PeerConnection, msg: dict[str, Any]) -> None:
        """Despacha uma mensagem recebida conforme `msg["type"]`."""
        mtype = msg.get("type")
        if mtype == MsgType.PING.value:
            self.keep_alive.on_ping(conn, msg)
        elif mtype == MsgType.PONG.value:
            self.keep_alive.on_pong(conn, msg)
        elif mtype == MsgType.SEND.value:
            self.router.on_send(conn, msg)
        elif mtype == MsgType.ACK.value:
            self.router.on_ack(conn, msg)
        elif mtype == MsgType.PUB.value:
            self.router.on_pub(conn, msg)
        elif mtype == MsgType.BYE.value:
            self._handle_bye(conn, msg)
        elif mtype == MsgType.BYE_OK.value:
            LOG.info("BYE_OK recebido de %s", conn.peer_id)
            conn.close("bye_ok")
        elif mtype == MsgType.HELLO.value:
            LOG.debug("HELLO inesperado de %s (já conectado)", conn.peer_id)
        else:
            LOG.warning("Tipo de mensagem desconhecido de %s: %r", conn.peer_id, mtype)

    def _handle_bye(self, conn: PeerConnection, msg: dict[str, Any]) -> None:
        """Responde BYE_OK a um BYE e encerra a conexão (estado CLOSED)."""
        LOG.info("BYE recebido de %s: %s", conn.peer_id, msg.get("reason", ""))
        try:
            bye_ok = {
                "type": MsgType.BYE_OK.value,
                "msg_id": new_msg_id(),
                "src": self.peer_id,
                "dst": conn.peer_id,
                "ttl": P2P_TTL,
            }
            conn.send(bye_ok)
        except OSError:
            pass
        if conn.peer_id is not None:
            self.peer_table.set_state(conn.peer_id, PeerState.CLOSED)
        conn.close("bye")

    def _on_conn_close(self, conn: PeerConnection) -> None:
        """Callback quando uma conexão fecha; atualiza estado e agenda reconexão."""
        if conn.peer_id is None:
            return
        self.peer_table.clear_conn(conn.peer_id, conn)
        self.keep_alive.clear_peer(conn.peer_id)
        entry = self.peer_table.get(conn.peer_id)
        if entry is None or self._stop.is_set():
            return
        # Fechamento intencional (BYE) não dispara reconexão.
        if entry.state == PeerState.CLOSED:
            return
        LOG.info("Conexão com %s caiu; estado -> STALE", conn.peer_id)
        self.peer_table.set_state(conn.peer_id, PeerState.STALE)
        self._schedule_reconnect(conn.peer_id)
