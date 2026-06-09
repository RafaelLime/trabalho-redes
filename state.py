"""state.py — Constantes do protocolo, tipos de mensagem e estados de conexão.

Módulo central de definições compartilhadas por todos os outros módulos.
Não contém lógica de rede; apenas constantes, enums e pequenos helpers de
construção/serialização de mensagens.
"""

from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Parâmetros fixos da spec
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "1.0"
FEATURES = ["ack", "metrics"]

# Transporte peer↔peer
MAX_MSG_SIZE = 32 * 1024  # 32 KiB (32768 bytes)
LINE_DELIMITER = b"\n"
ENCODING = "utf-8"

# TTL fixo em toda mensagem P2P (não decrementa)
P2P_TTL = 1

# Limites de validação (ver validation.py)
MAX_NAME_LEN = 64
MAX_NAMESPACE_LEN = 64
MIN_PORT = 1
MAX_PORT = 65535
MIN_REGISTER_TTL = 1
MAX_REGISTER_TTL = 86400

# Rendezvous
RENDEZVOUS_RATE_LIMIT = 50  # requisições por minuto


# ---------------------------------------------------------------------------
# Tipos de mensagem
# ---------------------------------------------------------------------------

class MsgType(str, enum.Enum):
    """Tipos de mensagem trocados entre peers (campo `type`)."""

    HELLO = "HELLO"
    HELLO_OK = "HELLO_OK"
    PING = "PING"
    PONG = "PONG"
    SEND = "SEND"
    ACK = "ACK"
    PUB = "PUB"
    BYE = "BYE"
    BYE_OK = "BYE_OK"


class RdvType(str, enum.Enum):
    """Comandos do servidor Rendezvous (campo `type`)."""

    REGISTER = "REGISTER"
    DISCOVER = "DISCOVER"
    UNREGISTER = "UNREGISTER"


# ---------------------------------------------------------------------------
# Estados de conexão / peer
# ---------------------------------------------------------------------------

class PeerState(str, enum.Enum):
    """Estado de um peer na PeerTable.

    KNOWN       — descoberto via DISCOVER, ainda não conectado.
    CONNECTING  — tentativa de conexão em andamento.
    ACTIVE      — handshake HELLO/HELLO_OK concluído, conexão viva.
    STALE       — não respondeu a PING; candidato a reconexão.
    FAILED      — esgotou max_reconnect_attempts.
    CLOSED      — encerrado via BYE/BYE_OK.
    """

    KNOWN = "KNOWN"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class Direction(str, enum.Enum):
    """Direção de uma conexão entre peers."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


# ---------------------------------------------------------------------------
# Helpers de identidade e mensagem
# ---------------------------------------------------------------------------

def make_peer_id(name: str, namespace: str) -> str:
    """Constrói `peer_id` no formato `name@namespace`."""
    return f"{name}@{namespace}"


def split_peer_id(peer_id: str) -> tuple[str, str]:
    """Separa um `peer_id` em `(name, namespace)`."""
    name, _, namespace = peer_id.partition("@")
    return name, namespace


def new_msg_id() -> str:
    """Gera um identificador único de mensagem."""
    return str(uuid.uuid4())


def utc_timestamp() -> str:
    """Timestamp ISO-8601 em UTC (ex.: `2025-10-27T10:00:00Z`)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def encode_line(msg: dict[str, Any]) -> bytes:
    """Serializa um dict para uma linha JSON UTF-8 terminada em `\\n`.

    TODO: validar tamanho ≤ MAX_MSG_SIZE antes de enviar.
    """
    raise NotImplementedError


def decode_line(line: bytes) -> dict[str, Any]:
    """Desserializa uma linha JSON recebida em dict.

    TODO: validar tamanho e tratar JSON inválido.
    """
    raise NotImplementedError
