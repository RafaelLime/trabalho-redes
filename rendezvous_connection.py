"""rendezvous_connection.py — Comunicação com o servidor Rendezvous (Critério 1).

Cada chamada (REGISTER/DISCOVER/UNREGISTER) abre uma conexão TCP nova, envia
uma única linha JSON, lê a resposta e fecha. Mantém também uma thread de
REGISTER recorrente para renovar o TTL antes de expirar.

Protocolo (ver https://github.com/mfcaetano/pyp2p-rdv):
    REGISTER   -> {"status": "OK", "ttl", "ip", "port"}
    DISCOVER   -> {"status": "OK", "peers": [...]}
    UNREGISTER -> {"status": "OK"}
    erro       -> {"status": "ERROR", "message": "bad_name" | ...}
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any, Optional

from state import RdvType, decode_line, encode_line
from validation import validate_register_fields

LOG = logging.getLogger("Rendezvous")

# Tempo máximo (s) aguardando conexão/resposta do servidor Rendezvous.
_RDV_TIMEOUT = 10.0


class RendezvousError(RuntimeError):
    """Erro retornado pelo servidor Rendezvous (status != OK)."""


class RendezvousConnection:
    """Cliente do servidor Rendezvous.

    Attributes:
        host, port    : endereço do servidor Rendezvous.
        public_ip     : IP público retornado no último REGISTER.
        public_port   : porta confirmada no último REGISTER.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.public_ip: Optional[str] = None
        self.public_port: Optional[int] = None
        self._renew_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- chamadas de baixo nível ------------------------------------------

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Abre conexão TCP curta, envia 1 linha JSON, lê resposta e fecha.

        Cada chamada usa uma conexão nova (send 1 linha, lê 1 resposta, fecha),
        conforme o protocolo Rendezvous. Levanta OSError em falha de rede e
        ValueError se a resposta não for uma linha JSON válida.
        """
        data = encode_line(payload)
        with socket.create_connection((self.host, self.port), timeout=_RDV_TIMEOUT) as sock:
            sock.sendall(data)
            # Lê até encontrar o '\n' delimitador (ou o servidor fechar).
            buf = bytearray()
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
        if not buf:
            raise ValueError("Rendezvous não retornou resposta")
        line = bytes(buf).split(b"\n", 1)[0]
        return decode_line(line)

    @staticmethod
    def _check_response(resp: dict[str, Any]) -> dict[str, Any]:
        """Verifica `status`; loga e levanta em caso de erro/rate limit.

        Retorna o próprio dict em caso de sucesso (status == "OK").
        Levanta RendezvousError com a mensagem do servidor caso contrário.
        """
        status = resp.get("status")
        if status == "OK":
            return resp
        message = resp.get("message", "<sem mensagem>")
        msg_lower = message.lower() if isinstance(message, str) else ""
        if "ban" in msg_lower or "rate" in msg_lower or status == "RATE_LIMIT":
            LOG.warning("Rate limit do Rendezvous atingido: %s", message)
        elif message == "peer_not_registered":
            # Condição benigna (ex.: DISCOVER em namespace vazio); o chamador decide.
            LOG.debug("Rendezvous: %s", message)
        else:
            LOG.warning("Rendezvous retornou erro: status=%s message=%s", status, message)
        raise RendezvousError(str(message))

    # -- API pública ------------------------------------------------------

    def register(self, namespace: str, name: str, port: int, ttl: int) -> dict[str, Any]:
        """Registra o peer no Rendezvous e guarda ip/port retornados."""
        validate_register_fields(namespace, name, port, ttl)
        payload = {
            "type": RdvType.REGISTER.value,
            "namespace": namespace,
            "name": name,
            "port": port,
            "ttl": ttl,
        }
        resp = self._check_response(self._request(payload))
        self.public_ip = resp.get("ip")
        self.public_port = resp.get("port", port)
        LOG.info(
            "REGISTER OK: %s@%s -> %s:%s (ttl=%ss)",
            name, namespace, self.public_ip, self.public_port, resp.get("ttl", ttl),
        )
        return resp

    def discover(self, namespace: Optional[str] = None) -> list[dict[str, Any]]:
        """Descobre peers (opcionalmente filtrando por namespace)."""
        payload: dict[str, Any] = {"type": RdvType.DISCOVER.value}
        if namespace is not None:
            payload["namespace"] = namespace
        try:
            resp = self._check_response(self._request(payload))
        except RendezvousError as exc:
            # Namespace sem peers: o servidor responde com erro em vez de
            # lista vazia. Tratamos como "nenhum peer" para não quebrar o loop.
            if "peer_not_registered" in str(exc):
                LOG.info("DISCOVER: nenhum peer registrado%s",
                         f" no namespace {namespace}" if namespace else "")
                return []
            raise
        peers = resp.get("peers", [])
        if not isinstance(peers, list):
            LOG.warning("DISCOVER: campo 'peers' inesperado: %r", peers)
            return []
        LOG.info(
            "DISCOVER OK: %d peer(s)%s",
            len(peers), f" no namespace {namespace}" if namespace else "",
        )
        return peers

    def unregister(self, namespace: str, name: str, port: int) -> None:
        """Remove o registro do peer no Rendezvous."""
        payload = {
            "type": RdvType.UNREGISTER.value,
            "namespace": namespace,
            "name": name,
            "port": port,
        }
        try:
            self._check_response(self._request(payload))
            LOG.info("UNREGISTER OK: %s@%s", name, namespace)
        except (OSError, ValueError, RendezvousError) as exc:
            # Falha no unregister não deve impedir o shutdown; apenas loga.
            LOG.warning("Falha ao executar UNREGISTER: %s", exc)

    # -- renovação automática de TTL --------------------------------------

    def start_renew(self, namespace: str, name: str, port: int, ttl: int) -> None:
        """Inicia thread que reenvia REGISTER a cada ~ttl/2 para renovar o TTL."""
        if self._renew_thread is not None and self._renew_thread.is_alive():
            LOG.debug("Thread de renovação já está ativa")
            return
        self._stop.clear()
        # Renova bem antes de expirar; nunca menos de 1s para não floodar.
        interval = max(1.0, ttl / 2)

        def _renew_loop() -> None:
            LOG.info("Renovação de TTL iniciada (a cada %.0fs)", interval)
            while not self._stop.wait(interval):
                try:
                    self.register(namespace, name, port, ttl)
                    LOG.debug("TTL renovado para %s@%s", name, namespace)
                except (OSError, ValueError, RendezvousError) as exc:
                    LOG.warning("Falha ao renovar REGISTER: %s", exc)
            LOG.info("Renovação de TTL encerrada")

        self._renew_thread = threading.Thread(
            target=_renew_loop, name="rdv-renew", daemon=True
        )
        self._renew_thread.start()

    def stop_renew(self) -> None:
        """Sinaliza parada da thread de renovação e aguarda seu término."""
        self._stop.set()
        thread = self._renew_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_RDV_TIMEOUT)
        self._renew_thread = None
