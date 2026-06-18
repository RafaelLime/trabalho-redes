"""validation.py — Validação de tipos e formatos dos campos (Rubrica).

Valida campos ANTES de cada REGISTER e ao receber comandos da CLI, além de
fazer a validação básica de mensagens P2P recebidas.

Regras:
- namespace : string até 64 caracteres
- name      : string até 64 caracteres
- port      : inteiro 1–65535
- ttl       : inteiro 1–86400 (segundos)
"""

from __future__ import annotations

from typing import Any

from state import (
    MAX_MSG_SIZE,
    MAX_NAME_LEN,
    MAX_NAMESPACE_LEN,
    MAX_PORT,
    MAX_REGISTER_TTL,
    MIN_PORT,
    MIN_REGISTER_TTL,
)


class ValidationError(ValueError):
    """Erro de validação de campo ou mensagem."""


def validate_name(name: Any) -> str:
    """Valida `name`: string não vazia de até 64 caracteres."""
    if not isinstance(name, str):
        raise ValidationError(f"name deve ser string, recebido {type(name).__name__}")
    if not name:
        raise ValidationError("name não pode ser vazio")
    if len(name) > MAX_NAME_LEN:
        raise ValidationError(
            f"name excede {MAX_NAME_LEN} caracteres (tem {len(name)})"
        )
    if "@" in name:
        raise ValidationError("name não pode conter '@'")
    return name


def validate_namespace(namespace: Any) -> str:
    """Valida `namespace`: string não vazia de até 64 caracteres."""
    if not isinstance(namespace, str):
        raise ValidationError(
            f"namespace deve ser string, recebido {type(namespace).__name__}"
        )
    if not namespace:
        raise ValidationError("namespace não pode ser vazio")
    if len(namespace) > MAX_NAMESPACE_LEN:
        raise ValidationError(
            f"namespace excede {MAX_NAMESPACE_LEN} caracteres (tem {len(namespace)})"
        )
    if "@" in namespace:
        raise ValidationError("namespace não pode conter '@'")
    return namespace


def validate_port(port: Any) -> int:
    """Valida `port`: inteiro em [1, 65535]."""
    # bool é subclasse de int — rejeitar explicitamente.
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValidationError(f"port deve ser inteiro, recebido {type(port).__name__}")
    if not (MIN_PORT <= port <= MAX_PORT):
        raise ValidationError(
            f"port fora da faixa [{MIN_PORT}, {MAX_PORT}]: {port}"
        )
    return port


def validate_ttl(ttl: Any) -> int:
    """Valida `ttl`: inteiro em [1, 86400] segundos."""
    if isinstance(ttl, bool) or not isinstance(ttl, int):
        raise ValidationError(f"ttl deve ser inteiro, recebido {type(ttl).__name__}")
    if not (MIN_REGISTER_TTL <= ttl <= MAX_REGISTER_TTL):
        raise ValidationError(
            f"ttl fora da faixa [{MIN_REGISTER_TTL}, {MAX_REGISTER_TTL}]: {ttl}"
        )
    return ttl


def validate_register_fields(namespace: Any, name: Any, port: Any, ttl: Any) -> None:
    """Valida todos os campos exigidos antes de um REGISTER.

    Levanta ValidationError no primeiro campo inválido.
    """
    validate_namespace(namespace)
    validate_name(name)
    validate_port(port)
    validate_ttl(ttl)


def validate_incoming_p2p(line: bytes) -> dict[str, Any]:
    """Validação básica de mensagem P2P recebida.

    Verifica tamanho ≤ MAX_MSG_SIZE, JSON válido e presença do campo `type`.
    Retorna o dict desserializado.
    """
    from state import decode_line

    if len(line) > MAX_MSG_SIZE:
        raise ValidationError(
            f"mensagem excede {MAX_MSG_SIZE} bytes (tem {len(line)})"
        )
    try:
        msg = decode_line(line)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if "type" not in msg:
        raise ValidationError("mensagem sem campo 'type'")
    if not isinstance(msg["type"], str):
        raise ValidationError("campo 'type' deve ser string")
    return msg
