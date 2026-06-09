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

from state import Direction, PeerState

LOG = logging.getLogger("PeerConn")


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

    # -- handshake --------------------------------------------------------

    def do_handshake_outbound(self) -> bool:
        """Envia HELLO e aguarda HELLO_OK (lado que disca).

        TODO: enviar HELLO, ler resposta, validar e preencher peer_id.
        """
        raise NotImplementedError

    def handle_hello_inbound(self, hello: dict[str, Any]) -> None:
        """Trata HELLO recebido e responde HELLO_OK (lado que aceita).

        TODO: preencher peer_id, responder HELLO_OK, marcar ACTIVE.
        """
        raise NotImplementedError

    # -- envio / recepção -------------------------------------------------

    def send(self, msg: dict[str, Any]) -> None:
        """Envia uma mensagem (thread-safe via lock por socket).

        TODO: encode_line, sendall sob self._send_lock.
        """
        raise NotImplementedError

    def start_reader(self) -> None:
        """Inicia a thread de leitura desta conexão."""
        self._alive = True
        self._reader_thread = threading.Thread(
            target=self._read_loop, name=f"reader-{self.peer_id}", daemon=True
        )
        self._reader_thread.start()

    def _read_loop(self) -> None:
        """Loop de leitura: acumula bytes, separa por '\\n', faz dispatch.

        TODO: recv em loop, separar linhas, validar tamanho/JSON,
        chamar self.on_message; fechar em erro/EOF.
        """
        raise NotImplementedError

    def close(self, reason: str = "") -> None:
        """Fecha o socket e encerra o reader de forma limpa.

        TODO: marcar estado, fechar socket, disparar on_close.
        """
        raise NotImplementedError


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
        """Cria o socket de escuta e inicia a thread de accept.

        TODO: bind/listen em 0.0.0.0:listen_port, thread chamando accept().
        """
        raise NotImplementedError

    def _accept_loop(self) -> None:
        """Aceita conexões e delega cada uma a on_accept.

        TODO: loop accept(), chamar self.on_accept(conn, addr).
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Para de aceitar e fecha o socket de escuta."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
