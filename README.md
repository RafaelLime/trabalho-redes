# Chat P2P — Trabalho de Redes

Cliente de **chat peer-to-peer (P2P)** com conexão direta, desenvolvido como
trabalho de programação da disciplina de Redes. Cada nó (*peer*) atua
simultaneamente como cliente e servidor: registra-se em um **servidor
Rendezvous**, descobre outros peers ativos, mantém **conexões TCP persistentes**
e troca mensagens em tempo real.

> Não há relay nem múltiplos saltos (TTL fixo em `1`): cada peer comunica-se
> diretamente apenas com os peers alcançáveis.

A especificação completa do protocolo está em [`specs.md`](specs.md).

---

## Funcionalidades

- **Registro e descoberta** automáticos via servidor Rendezvous
  (`REGISTER` / `DISCOVER` / `UNREGISTER`).
- **Handshake** entre peers (`HELLO` / `HELLO_OK`) sobre TCP.
- **Mensagens diretas** com confirmação (`SEND` / `ACK`).
- **Difusão** por namespace (`#namespace`) ou broadcast global (`*`) via `PUB`.
- **Keep-alive** com `PING` / `PONG` e cálculo de RTT.
- **Reconexão** automática com backoff exponencial.
- **Encerramento limpo** das sessões (`BYE` / `BYE_OK`).
- **Interface de linha de comando (CLI)** e logs com observabilidade.

---

## Requisitos

### Sistema

- **Python 3.9 ou superior** (testado com Python 3.13).
- Sistema operacional Linux, macOS ou Windows.
- Acesso à rede para alcançar o servidor Rendezvous.

### Bibliotecas

Nenhuma dependência externa. O projeto utiliza **apenas a biblioteca padrão do
Python** (`socket`, `threading`, `json`, `logging`, `argparse`, `uuid`,
`dataclasses`, `enum`, `datetime`, `shlex`). Não é necessário `pip install`.

---

## Configuração

Os parâmetros ficam em [`config.json`](config.json):

| Chave                    | Descrição                                                  |
| ------------------------ | ---------------------------------------------------------- |
| `name`                   | Nome único do peer dentro do namespace (ex.: `alice`)      |
| `namespace`              | Agrupador lógico (ex.: `CIC`, `UnB`)                       |
| `listen_port`            | Porta TCP local de escuta para conexões inbound            |
| `rendezvous_host`        | Endereço do servidor Rendezvous                            |
| `rendezvous_port`        | Porta do servidor Rendezvous                               |
| `ping_interval`          | Intervalo (s) entre PINGs de keep-alive                    |
| `ack_timeout`            | Tempo (s) para aguardar ACK antes de avisar timeout        |
| `discover_interval`      | Intervalo (s) entre descobertas periódicas de peers        |
| `max_reconnect_attempts` | Número máximo de tentativas de reconexão                   |
| `log_level`              | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`)         |

O `peer_id` resultante é `name@namespace` (ex.: `alice@CIC`).

Por padrão, o `config.json` aponta para o servidor Rendezvous público de testes:

```
pyp2p.mfcaetano.cc  (45.171.101.167)  — porta 8080
```

Documentação do protocolo Rendezvous: <https://github.com/mfcaetano/pyp2p-rdv>

---

## Como executar

1. (Opcional, recomendado) crie e ative um ambiente virtual:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   ```

2. Ajuste o [`config.json`](config.json) com o `name`, `namespace` e
   `listen_port` desejados.

3. Execute o cliente:

   ```bash
   python3 main.py --config config.json
   ```

   O argumento `--config` é opcional (o padrão é `config.json`).

Para rodar **dois peers na mesma máquina**, use cópias do config com `name` e
`listen_port` diferentes:

```bash
python3 main.py --config config-alice.json
python3 main.py --config config-bob.json   # em outro terminal
```

---

## Comandos da CLI

Após iniciar, use os comandos abaixo no prompt da aplicação:

| Comando                          | Função                                       |
| -------------------------------- | -------------------------------------------- |
| `/peers [* \| #namespace]`       | Descobrir e listar peers                     |
| `/msg <peer_id> <mensagem>`      | Enviar mensagem direta (`SEND`)              |
| `/pub * <mensagem>`              | Enviar broadcast global                      |
| `/pub #<namespace> <mensagem>`   | Enviar mensagem a todos de um namespace      |
| `/conn`                          | Mostrar conexões ativas (inbound/outbound)   |
| `/rtt`                           | Exibir RTT médio por peer                    |
| `/reconnect`                     | Forçar reconciliação de peers                |
| `/log <nível>`                   | Ajustar o nível de log em tempo de execução  |
| `/quit`                          | Encerrar a aplicação (`BYE` + `UNREGISTER`)  |

---

## Estrutura do projeto

```
.
├── main.py                    # Ponto de entrada: config, logging e inicialização
├── p2p_client.py              # Lógica principal (registro, descoberta, reconexão)
├── rendezvous_connection.py   # Comunicação com o servidor Rendezvous
├── peer_connection.py         # Conexões TCP e servidor de escuta entre peers
├── message_router.py          # Envio e publicação de mensagens (SEND/PUB/ACK)
├── keep_alive.py              # Gerenciamento de PING/PONG e RTT
├── peer_table.py              # Tabela de peers, estados e reconexão
├── state.py                   # Tipos, estados e estruturas de dados dos peers
├── cli.py                     # Interface de linha de comando
├── validation.py              # Validação de mensagens e identidades
├── config.json                # Arquivo de configuração de exemplo
└── specs.md                   # Especificação completa do protocolo
```

---

## Protocolo

O transporte é **TCP** com mensagens em **JSON UTF-8 delimitadas por `\n`**
(tamanho máximo de 32 KiB). Os tipos de mensagem trocados entre peers são:
`HELLO` / `HELLO_OK`, `PING` / `PONG`, `SEND` / `ACK`, `PUB` e
`BYE` / `BYE_OK`. Consulte [`specs.md`](specs.md) para o formato detalhado de
cada mensagem e os critérios de avaliação.
