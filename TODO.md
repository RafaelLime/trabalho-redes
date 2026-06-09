# TODO — Chat P2P (Trabalho de Redes)

Cliente de Chat P2P em **Python (stdlib)** que se registra num servidor Rendezvous,
descobre peers automaticamente, mantém conexões TCP diretas e troca mensagens em
tempo real. Sem relay / sem multi-hop (`ttl` fixo em `1`).

> Servidor Rendezvous de testes: `pyp2p.mfcaetano.cc:8080` (IP 45.171.101.167)
> Doc do protocolo Rendezvous: https://github.com/mfcaetano/pyp2p-rdv

---

## Parâmetros fixos (da spec)

- [ ] Transporte peer↔peer: TCP, JSON UTF-8 delimitado por `\n`, máx **32 KiB**
- [ ] `ttl` = `1` em toda mensagem P2P (não decrementa)
- [ ] Keep-alive: PING a cada **30 s** (configurável via `config.json`)
- [ ] ACK ausente após **5 s** → log de timeout
- [ ] Identidade `name@namespace`; escopos: unicast `peer_id`, namespace `#ns`, broadcast `*`
- [ ] Rendezvous: 1 conexão TCP curta por comando; reenviar REGISTER p/ renovar TTL; respeitar rate limit 50 req/min

---

## 0. Scaffold

- [x] `config.json` — `name`, `namespace`, `listen_port`, `rendezvous_host`,
      `rendezvous_port`, `ping_interval`, `ack_timeout`, `discover_interval`,
      `max_reconnect_attempts`, `log_level`
- [x] `main.py` — ler args/config, inicializar logging, subir `P2PClient`
- [x] Logging formatado `[Módulo] mensagem` com timestamp + nível
- [x] Esqueleto dos módulos (imports/classes vazias)

## 0.5 Validação de campos — `validation.py`  → Rubrica

- [ ] `namespace`: string até **64 caracteres**
- [ ] `name`: string até **64 caracteres**
- [ ] `port`: inteiro **1–65535**
- [ ] `ttl`: inteiro em segundos **1–86400**
- [ ] Validar **antes** de cada REGISTER e ao receber comandos da CLI
- [ ] Validação básica das mensagens P2P recebidas (campo `type`, tamanho ≤ 32 KiB)

## 1. Rendezvous — `rendezvous_connection.py`  → Critério 1

- [ ] `register(namespace, name, port, ttl)` → guarda `ip`/`port` retornados
- [ ] `discover(namespace=None)` → lista de peers
- [ ] `unregister(namespace, name, port)`
- [ ] Conexão TCP nova por chamada (envia 1 linha JSON, lê resposta, fecha)
- [ ] Tratar respostas de erro (`bad_*`, rate limit) com log
- [ ] **Thread de REGISTER recorrente** — renova antes do TTL expirar (ex.: a cada `ttl/2`)

## 2. Conexões entre peers — `peer_connection.py`  → Critério 2

- [ ] Servidor TCP de escuta em `listen_port` (aceita conexões inbound)
- [ ] Dialer outbound (conecta a peers descobertos)
- [ ] Handshake **HELLO / HELLO_OK** (com `peer_id`, `version`, `features`, `ttl`)
- [ ] Framing por `\n` na leitura/escrita; rejeitar linhas > 32 KiB
- [ ] Loop de leitura (1 thread por conexão) + dispatch por `type`
- [ ] Envio thread-safe (lock por socket)
- [ ] **Dedupe**: não discar a um peer que já abriu conexão com você (por `peer_id`)

## 3. Keep-alive — `keep_alive.py`  → Critérios 2 e 3

- [ ] Thread envia **PING** a cada 30 s (msg_id uuid + timestamp)
- [ ] Responder **PONG** ao receber PING
- [ ] Casar PONG por `msg_id` e calcular **RTT**
- [ ] Marcar peer como `STALE` se não responde
- [ ] Log `Sent N PINGs | Average RTT = X ms`

## 4. Mensageria — `message_router.py`  → Critério 3

- [ ] `send(dst, payload)` → **SEND** com `require_ack=true`
- [ ] Responder **ACK** ao receber SEND endereçado a si
- [ ] Timeout de 5 s sem ACK → log de aviso
- [ ] `pub("#ns", payload)` → **PUB** namespace-cast p/ peers do namespace
- [ ] `pub("*", payload)` → **PUB** broadcast p/ todos os conectados
- [ ] `msg_id` via `uuid.uuid4()`, timestamps ISO-8601 UTC

## 5. Encerramento  → Critério 4

- [ ] **BYE / BYE_OK** por conexão (com `reason`)
- [ ] `UNREGISTER` no Rendezvous ao sair
- [ ] Fechar sockets e threads de forma limpa (shutdown)

## 6. Descoberta + reconexão — `p2p_client.py` + `peer_table.py`  → Critério 5

- [ ] Registro inicial no Rendezvous
- [ ] Thread de **DISCOVER periódico** (intervalo configurável)
- [ ] Conectar automaticamente a peers novos descobertos
- [ ] `PeerTable` com estados `ACTIVE` / `STALE` / `CONNECTING`
- [ ] Reconexão com **backoff exponencial**, limite `max_reconnect_attempts`
- [ ] Reenvio periódico de REGISTER para renovar TTL no servidor

## 7. Interface CLI — `cli.py`  → Critério 6

- [ ] `/peers [* | #namespace]` — descobrir e listar peers
- [ ] `/msg <peer_id> <mensagem>` — mensagem direta
- [ ] `/pub * <mensagem>` — broadcast global
- [ ] `/pub #<namespace> <mensagem>` — mensagem p/ namespace
- [ ] `/conn` — conexões ativas (inbound/outbound)
- [ ] `/rtt` — RTT médio por peer
- [ ] `/reconnect` — forçar reconciliação de peers
- [ ] `/log <Nível>` — ajustar nível de log
- [ ] `/quit` — encerrar (BYE + UNREGISTER)

## 8. Entrega

- [ ] `README.md` — como rodar (`python main.py --config config.json`) + notas de NAT
- [ ] Revisar logs/observabilidade (exemplos da spec)

---

## Cenários de teste mínimos (validação final)

- [ ] 1. Conexão direta — 2 peers no mesmo namespace trocando `/msg` e `/pub #ns`
- [ ] 2. Descoberta automática — peers se registram e se descobrem periodicamente
- [ ] 3. Keep-alive — PING/PONG e RTT aparecem nos logs
- [ ] 4. Reconexão — peer cai, vira STALE, reconecta automaticamente com backoff
- [ ] 5. Encerramento — BYE/BYE_OK + UNREGISTER funcionando
- [ ] 6. CLI — `/msg`, `/pub`, `/rtt`, `/conn`, `/reconnect`, `/log`, `/quit`

## Rubrica do avaliador (`requirements.txt`) — todas devem ser "Sim"

- [ ] Carrega configurações de arquivo `.json`
- [ ] Solução modular (rendezvous, conexões de peers, UI... em módulos separados)
- [ ] Valida tipos/formatos dos campos (`namespace`/`name` ≤64, `port` 1–65535, `ttl` 1–86400)
- [ ] Faz REGISTER no Rendezvous
- [ ] REGISTER recorrente — renova automaticamente após expirar o TTL
- [ ] Usa UNREGISTER ao finalizar a execução
- [ ] Implementa DISCOVER corretamente e de forma recorrente
- [ ] Ao receber a lista do DISCOVER, inicia processo de conexão nos peers
- [ ] Diferencia peers já conhecidos dos novos a cada DISCOVER
- [ ] Distingue estado da conexão por peer (conectado / tentando / falha)
- [ ] Ao conectar, executa HELLO / HELLO_OK
- [ ] Aceita conexão e responde a um HELLO com HELLO_OK
- [ ] Não conecta a um peer que já se conectou ao seu cliente (dedupe)
- [ ] Executa PING / PONG periódico (keep-alive)
- [ ] Responde com PONG ao receber PING
- [ ] Implementa mensagem SEND
- [ ] Responde com ACK ao receber SEND
- [ ] Implementa PUB para namespace-cast
- [ ] Implementa PUB para broadcast
- [ ] Implementa desconexão BYE / BYE_OK
- [ ] Responde BYE_OK ao receber BYE e fecha a conexão (estado → encerrada)

## Módulos (sugestão da spec)

`main.py` · `p2p_client.py` · `rendezvous_connection.py` · `peer_connection.py` ·
`message_router.py` · `keep_alive.py` · `peer_table.py` · `state.py` ·
`validation.py` · `cli.py`
