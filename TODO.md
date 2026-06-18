# TODO — Chat P2P (Trabalho de Redes)

Cliente de Chat P2P em **Python (stdlib)** que se registra num servidor Rendezvous,
descobre peers automaticamente, mantém conexões TCP diretas e troca mensagens em
tempo real. Sem relay / sem multi-hop (`ttl` fixo em `1`).

> Servidor Rendezvous de testes: `pyp2p.mfcaetano.cc:8080` (IP 45.171.101.167)
> Doc do protocolo Rendezvous: https://github.com/mfcaetano/pyp2p-rdv

---

## Parâmetros fixos (da spec)

- [x] Transporte peer↔peer: TCP, JSON UTF-8 delimitado por `\n`, máx **32 KiB**
- [x] `ttl` = `1` em toda mensagem P2P (não decrementa)
- [x] Keep-alive: PING a cada **30 s** (configurável via `config.json`)
- [x] ACK ausente após **5 s** → log de timeout
- [x] Identidade `name@namespace`; escopos: unicast `peer_id`, namespace `#ns`, broadcast `*`
- [x] Rendezvous: 1 conexão TCP curta por comando; reenviar REGISTER p/ renovar TTL; respeitar rate limit 50 req/min

---

## 0. Scaffold

- [x] `config.json` — `name`, `namespace`, `listen_port`, `rendezvous_host`,
      `rendezvous_port`, `ping_interval`, `ack_timeout`, `discover_interval`,
      `max_reconnect_attempts`, `log_level`
- [x] `main.py` — ler args/config, inicializar logging, subir `P2PClient`
- [x] Logging formatado `[Módulo] mensagem` com timestamp + nível
- [x] Esqueleto dos módulos (imports/classes vazias)

## 0.5 Validação de campos — `validation.py`  → Rubrica

- [x] `namespace`: string até **64 caracteres**
- [x] `name`: string até **64 caracteres**
- [x] `port`: inteiro **1–65535**
- [x] `ttl`: inteiro em segundos **1–86400**
- [x] Validar **antes** de cada REGISTER e ao receber comandos da CLI
- [x] Validação básica das mensagens P2P recebidas (campo `type`, tamanho ≤ 32 KiB)

## 1. Rendezvous — `rendezvous_connection.py`  → Critério 1

- [x] `register(namespace, name, port, ttl)` → guarda `ip`/`port` retornados
- [x] `discover(namespace=None)` → lista de peers
- [x] `unregister(namespace, name, port)`
- [x] Conexão TCP nova por chamada (envia 1 linha JSON, lê resposta, fecha)
- [x] Tratar respostas de erro (`bad_*`, rate limit) com log
- [x] **Thread de REGISTER recorrente** — renova antes do TTL expirar (ex.: a cada `ttl/2`)

## 2. Conexões entre peers — `peer_connection.py`  → Critério 2

- [x] Servidor TCP de escuta em `listen_port` (aceita conexões inbound)
- [x] Dialer outbound (conecta a peers descobertos)
- [x] Handshake **HELLO / HELLO_OK** (com `peer_id`, `version`, `features`, `ttl`)
- [x] Framing por `\n` na leitura/escrita; rejeitar linhas > 32 KiB
- [x] Loop de leitura (1 thread por conexão) + dispatch por `type`
- [x] Envio thread-safe (lock por socket)
- [x] **Dedupe**: não discar a um peer que já abriu conexão com você (por `peer_id`)

## 3. Keep-alive — `keep_alive.py`  → Critérios 2 e 3

- [x] Thread envia **PING** a cada 30 s (msg_id uuid + timestamp)
- [x] Responder **PONG** ao receber PING
- [x] Casar PONG por `msg_id` e calcular **RTT**
- [x] Marcar peer como `STALE` se não responde
- [x] Log `Sent N PINGs | Average RTT = X ms`

## 4. Mensageria — `message_router.py`  → Critério 3

- [x] `send(dst, payload)` → **SEND** com `require_ack=true`
- [x] Responder **ACK** ao receber SEND endereçado a si
- [x] Timeout de 5 s sem ACK → log de aviso
- [x] `pub("#ns", payload)` → **PUB** namespace-cast p/ peers do namespace
- [x] `pub("*", payload)` → **PUB** broadcast p/ todos os conectados
- [x] `msg_id` via `uuid.uuid4()`, timestamps ISO-8601 UTC

## 5. Encerramento  → Critério 4

- [x] **BYE / BYE_OK** por conexão (com `reason`)
- [x] `UNREGISTER` no Rendezvous ao sair
- [x] Fechar sockets e threads de forma limpa (shutdown)

## 6. Descoberta + reconexão — `p2p_client.py` + `peer_table.py`  → Critério 5

- [x] Registro inicial no Rendezvous
- [x] Thread de **DISCOVER periódico** (intervalo configurável)
- [x] Conectar automaticamente a peers novos descobertos
- [x] `PeerTable` com estados `ACTIVE` / `STALE` / `CONNECTING`
- [x] Reconexão com **backoff exponencial**, limite `max_reconnect_attempts`
- [x] Reenvio periódico de REGISTER para renovar TTL no servidor

## 7. Interface CLI — `cli.py`  → Critério 6

- [x] `/peers [* | #namespace]` — descobrir e listar peers
- [x] `/msg <peer_id> <mensagem>` — mensagem direta
- [x] `/pub * <mensagem>` — broadcast global
- [x] `/pub #<namespace> <mensagem>` — mensagem p/ namespace
- [x] `/conn` — conexões ativas (inbound/outbound)
- [x] `/rtt` — RTT médio por peer
- [x] `/reconnect` — forçar reconciliação de peers
- [x] `/log <Nível>` — ajustar nível de log
- [x] `/quit` — encerrar (BYE + UNREGISTER)

## 8. Entrega

- [ ] `README.md` — como rodar (`python main.py --config config.json`) + notas de NAT
- [ ] Revisar logs/observabilidade (exemplos da spec)

---

## Cenários de teste mínimos (validação final)

- [x] 1. Conexão direta — 2 peers no mesmo namespace trocando `/msg` e `/pub #ns`
- [x] 2. Descoberta automática — peers se registram e se descobrem periodicamente
- [x] 3. Keep-alive — PING/PONG e RTT aparecem nos logs
- [x] 4. Reconexão — peer cai, vira STALE, reconecta automaticamente com backoff
- [x] 5. Encerramento — BYE/BYE_OK + UNREGISTER funcionando
- [x] 6. CLI — `/msg`, `/pub`, `/rtt`, `/conn`, `/reconnect`, `/log`, `/quit`

## Rubrica do avaliador (`requirements.txt`) — todas devem ser "Sim"

- [x] Carrega configurações de arquivo `.json`
- [x] Solução modular (rendezvous, conexões de peers, UI... em módulos separados)
- [x] Valida tipos/formatos dos campos (`namespace`/`name` ≤64, `port` 1–65535, `ttl` 1–86400)
- [x] Faz REGISTER no Rendezvous
- [x] REGISTER recorrente — renova automaticamente após expirar o TTL
- [x] Usa UNREGISTER ao finalizar a execução
- [x] Implementa DISCOVER corretamente e de forma recorrente
- [x] Ao receber a lista do DISCOVER, inicia processo de conexão nos peers
- [x] Diferencia peers já conhecidos dos novos a cada DISCOVER
- [x] Distingue estado da conexão por peer (conectado / tentando / falha)
- [x] Ao conectar, executa HELLO / HELLO_OK
- [x] Aceita conexão e responde a um HELLO com HELLO_OK
- [x] Não conecta a um peer que já se conectou ao seu cliente (dedupe)
- [x] Executa PING / PONG periódico (keep-alive)
- [x] Responde com PONG ao receber PING
- [x] Implementa mensagem SEND
- [x] Responde com ACK ao receber SEND
- [x] Implementa PUB para namespace-cast
- [x] Implementa PUB para broadcast
- [x] Implementa desconexão BYE / BYE_OK
- [x] Responde BYE_OK ao receber BYE e fecha a conexão (estado → encerrada)

## Módulos (sugestão da spec)

`main.py` · `p2p_client.py` · `rendezvous_connection.py` · `peer_connection.py` ·
`message_router.py` · `keep_alive.py` · `peer_table.py` · `state.py` ·
`validation.py` · `cli.py`
