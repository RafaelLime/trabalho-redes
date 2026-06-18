"""peer_connection.py — Conexões TCP entre peers (Critério 2).

Contém:
  - PeerServer     : socket de escuta que aceita conexões inbound.
  - PeerConnection : uma conexão TCP individual (inbound ou outbound), com
                     handshake HELLO/HELLO_OK, framing por '\\n', loop de
                     leitura em thread própria e envio thread-safe.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Callable, Optional

from state import (
    FEATURES,
    MAX_MSG_SIZE,
    MsgType,
    P2P_TTL,
    PROTOCOL_VERSION,
    Direction,
    PeerState,
    decode_line,
    encode_line,
)

LOG = logging.getLogger("PeerConn")

# Tempo máximo (s) aguardando a mensagem de handshake (HELLO/HELLO_OK).
_HANDSHAKE_TIMEOUT = 10.0


class PeerConnection:
    """Representa uma conexão TCP com um único peer.

    Attributes:
        sock        : socket conectado.
        direction   : INBOUND ou OUTBOUND.
        peer_id     : identidade do peer remoto (preenchida no handshake).
        on_message  : callback chamado para cada mensagem recebida válida.
    """

    def __init__(
        self,
        sock: socket.socket,
        direction: Direction,
        local_peer_id: str,
        on_message: Callable[["PeerConnection", dict[str, Any]], None],
        on_close: Optional[Callable[["PeerConnection"], None]] = None,
    ) -> None:
        self.sock = sock
        self.direction = direction
        self.local_peer_id = local_peer_id
        self.peer_id: Optional[str] = None
        self.on_message = on_message
        self.on_close = on_close
        self.state = PeerState.CONNECTING
        self._send_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._buf = b""
        self._alive = False
        self._closed = False
        self._close_lock = threading.Lock()

    # -- handshake --------------------------------------------------------

    def do_handshake_outbound(self) -> bool:
        """Envia HELLO e aguarda HELLO_OK (lado que disca).

        Retorna True se o handshake foi concluído e `peer_id` preenchido.
        """
        hello = {
            "type": MsgType.HELLO.value,
            "peer_id": self.local_peer_id,
            "version": PROTOCOL_VERSION,
            "features": FEATURES,
            "ttl": P2P_TTL,
        }
        try:
            self.send(hello)
        except OSError:
            return False
        resp = self._recv_message(timeout=_HANDSHAKE_TIMEOUT)
        if resp is None:
            LOG.warning("Handshake outbound: sem resposta")
            return False
        if resp.get("type") != MsgType.HELLO_OK.value:
            LOG.warning(
                "Handshake outbound: esperado HELLO_OK, recebido %s", resp.get("type")
            )
            return False
        self.peer_id = resp.get("peer_id")
        self.state = PeerState.ACTIVE
        LOG.info("Handshake OK (outbound) com %s", self.peer_id)
        return True

    def recv_hello(self, timeout: float = _HANDSHAKE_TIMEOUT) -> Optional[dict[str, Any]]:
        """Lê a primeira mensagem da conexão inbound (espera-se um HELLO)."""
        return self._recv_message(timeout=timeout)

    def handle_hello_inbound(self, hello: dict[str, Any]) -> None:
        """Trata HELLO recebido e responde HELLO_OK (lado que aceita)."""
        self.peer_id = hello.get("peer_id")
        hello_ok = {
            "type": MsgType.HELLO_OK.value,
            "peer_id": self.local_peer_id,
            "version": PROTOCOL_VERSION,
            "features": FEATURES,
            "ttl": P2P_TTL,
        }
        self.send(hello_ok)
        self.state = PeerState.ACTIVE
        LOG.info("Handshake OK (inbound) com %s", self.peer_id)

    # -- envio / recepção -------------------------------------------------

    def send(self, msg: dict[str, Any]) -> None:
        """Envia uma mensagem (thread-safe via lock por socket).

        Levanta OSError se a escrita no socket falhar (e fecha a conexão).
        """
        data = encode_line(msg)
        with self._send_lock:
            try:
                self.sock.sendall(data)
            except OSError as exc:
                LOG.warning("Falha ao enviar para %s: %s", self.peer_id, exc)
                # Fecha fora do lock para evitar reentrância com on_close.
                threading.Thread(
                    target=self.close, args=("send error",), daemon=True
                ).start()
                raise

    def _recv_message(self, timeout: Optional[float] = None) -> Optional[dict[str, Any]]:
        """Lê uma única mensagem (linha terminada em '\\n') do socket.

        Usado no handshake, antes da thread de leitura iniciar. Bytes lidos
        além da linha ficam em self._buf para o read loop subsequente.
        """
        self.sock.settimeout(timeout)
        try:
            while b"\n" not in self._buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None  # EOF
                self._buf += chunk
                if len(self._buf) > MAX_MSG_SIZE and b"\n" not in self._buf:
                    LOG.warning("Linha de handshake excede %d bytes", MAX_MSG_SIZE)
                    return None
        except (socket.timeout, OSError) as exc:
            LOG.warning("Erro ao ler handshake: %s", exc)
            return None
        finally:
            try:
                self.sock.settimeout(None)
            except OSError:
                pass
        line, _, self._buf = self._buf.partition(b"\n")
        try:
            return decode_line(line)
        except ValueError as exc:
            LOG.warning("Handshake com mensagem inválida: %s", exc)
            return None

    def start_reader(self) -> None:
        """Inicia a thread de leitura desta conexão."""
        self._alive = True
        self._reader_thread = threading.Thread(
            target=self._read_loop, name=f"reader-{self.peer_id}", daemon=True
        )
        self._reader_thread.start()

    def _read_loop(self) -> None:
        """Loop de leitura: acumula bytes, separa por '\\n', faz dispatch."""
        try:
            while self._alive:
                if b"\n" not in self._buf:
                    try:
                        chunk = self.sock.recv(4096)
                    except OSError:
                        break
                    if not chunk:
                        break  # EOF: peer fechou
                    self._buf += chunk
                    if len(self._buf) > MAX_MSG_SIZE and b"\n" not in self._buf:
                        LOG.warning(
                            "Linha excede %d bytes de %s; fechando",
                            MAX_MSG_SIZE, self.peer_id,
                        )
                        break
                    continue
                line, _, self._buf = self._buf.partition(b"\n")
                if not line:
                    continue
                try:
                    msg = decode_line(line)
                except ValueError as exc:
                    LOG.warning("Mensagem inválida de %s: %s", self.peer_id, exc)
                    continue
                try:
                    self.on_message(self, msg)
                except Exception:  # noqa: BLE001 — isolar erro de um handler
                    LOG.exception("Erro ao processar mensagem de %s", self.peer_id)
        finally:
            self.close("reader exit")

    def close(self, reason: str = "") -> None:
        """Fecha o socket e encerra o reader de forma limpa (idempotente)."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._alive = False
        self.state = PeerState.CLOSED
        try:
            self.sock.close()
        except OSError:
            pass
        if reason:
            LOG.info("Conexão com %s fechada: %s", self.peer_id, reason)
        if self.on_close is not None:
            try:
                self.on_close(self)
            except Exception:  # noqa: BLE001
                LOG.exception("Erro no callback on_close de %s", self.peer_id)


class PeerServer:
    """Servidor TCP que escuta em `listen_port` e aceita conexões inbound."""

    def __init__(
        self,
        listen_port: int,
        local_peer_id: str,
        on_accept: Callable[[socket.socket, tuple], None],
    ) -> None:
        self.listen_port = listen_port
        self.local_peer_id = local_peer_id
        self.on_accept = on_accept
        self._server_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        """Cria o socket de escuta e inicia a thread de accept."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.listen_port))
        sock.listen(16)
        self._server_sock = sock
        self._running = True
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="peer-accept", daemon=True
        )
        self._accept_thread.start()
        LOG.info("Servidor de escuta ativo em 0.0.0.0:%d", self.listen_port)

    def _accept_loop(self) -> None:
        """Aceita conexões e delega cada uma a on_accept."""
        assert self._server_sock is not None
        while self._running:
            try:
                conn, addr = self._server_sock.accept()
            except OSError:
                break  # socket fechado em stop()
            if not self._running:
                try:
                    conn.close()
                except OSError:
                    pass
                break
            LOG.info("Conexão inbound de %s:%d", addr[0], addr[1])
            try:
                self.on_accept(conn, addr)
            except Exception:  # noqa: BLE001
                LOG.exception("Erro ao tratar conexão inbound de %s", addr)

    def stop(self) -> None:
        """Para de aceitar e fecha o socket de escuta."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
