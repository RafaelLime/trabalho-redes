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
    """Valida `name`: string não vazia de até 64 caracteres.

    TODO: implementar checagem de tipo, vazio e tamanho.
    """
    raise NotImplementedError


def validate_namespace(namespace: Any) -> str:
    """Valida `namespace`: string não vazia de até 64 caracteres.

    TODO: implementar checagem de tipo, vazio e tamanho.
    """
    raise NotImplementedError


def validate_port(port: Any) -> int:
    """Valida `port`: inteiro em [1, 65535].

    TODO: implementar checagem de tipo e faixa.
    """
    raise NotImplementedError


def validate_ttl(ttl: Any) -> int:
    """Valida `ttl`: inteiro em [1, 86400] segundos.

    TODO: implementar checagem de tipo e faixa.
    """
    raise NotImplementedError


def validate_register_fields(namespace: Any, name: Any, port: Any, ttl: Any) -> None:
    """Valida todos os campos exigidos antes de um REGISTER.

    TODO: chamar os validadores individuais e agregar erros.
    """
    raise NotImplementedError


def validate_incoming_p2p(line: bytes) -> dict[str, Any]:
    """Validação básica de mensagem P2P recebida.

    Verifica tamanho ≤ MAX_MSG_SIZE, JSON válido e presença do campo `type`.

    TODO: implementar e retornar o dict desserializado.
    """
    raise NotImplementedError
