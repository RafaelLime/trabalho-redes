"""main.py — Ponto de entrada da aplicação.

Lê argumentos/config, inicializa o logging e sobe o P2PClient com a CLI.

Uso:
    python main.py --config config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

# Campos obrigatórios esperados em config.json.
REQUIRED_KEYS = (
    "name",
    "namespace",
    "listen_port",
    "rendezvous_host",
    "rendezvous_port",
    "ping_interval",
    "ack_timeout",
    "discover_interval",
    "max_reconnect_attempts",
    "log_level",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Lê os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Cliente de Chat P2P (Trabalho de Redes)")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Caminho do arquivo de configuração JSON (padrão: config.json)",
    )
    return parser.parse_args(argv)


def load_config(path: str) -> dict[str, Any]:
    """Carrega e valida a presença das chaves do config.json."""
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise ValueError(f"Chaves ausentes em {path}: {', '.join(missing)}")
    return config


def setup_logging(level: str) -> None:
    """Configura o logging com formato `[Módulo] mensagem`, timestamp e nível."""
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    """Inicializa e executa o cliente. Retorna o código de saída do processo."""
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro ao carregar configuração: {exc}", file=sys.stderr)
        return 1

    setup_logging(config["log_level"])
    log = logging.getLogger("main")
    log.info("Iniciando cliente P2P: %s@%s", config["name"], config["namespace"])

    # Imports adiados para que o scaffold rode mesmo com módulos incompletos.
    from cli import CLI
    from p2p_client import P2PClient

    client = P2PClient(config)
    try:
        client.start()
        CLI(client).run()
    except KeyboardInterrupt:
        log.info("Interrompido pelo usuário.")
    finally:
        client.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
