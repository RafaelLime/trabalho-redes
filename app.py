# Integração do backend P2P com a interface React via Eel.

import logging
import threading
import time
from typing import Any

import eel
from p2p_client import P2PClient
from state import utc_timestamp, new_msg_id

# Referência global para as funções expostas do Eel acessarem a classe App
_APP_INSTANCE = None

class EelLogHandler(logging.Handler):
    """Captura os logs do Python e envia para o painel do React."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            eel.receiveEvent({
                "type": "LOG",
                "level": record.levelname.lower(),
                "message": msg,
                "timestamp": utc_timestamp()
            })()
        except Exception:
            pass

class P2PGUIApp:
    """
    Classe principal para interliagação das funções de backend
    com as funções de interface do usuário em React.
    O front é atualizado a partir de hooks e states definidos.
    """

    def __init__(self) -> None:

        # Captura a instância sendo usada atualmente
        global _APP_INSTANCE
        _APP_INSTANCE = self
        
        self.client: P2PClient | None = None
        self.config: dict[str, Any] = {}
        self._sync_thread: threading.Thread | None = None
        self._running = False

    def setup_logging(self) -> None:
        """Adiciona o handler para mandar os logs pro frontend."""
        logger = logging.getLogger()
        handler = EelLogHandler()
        handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
        logger.addHandler(handler)

    def start_ui(self, dev_mode: bool = True) -> None:
        """Inicia a janela do Eel."""
        self.setup_logging()
        
        # Usa a pasta dist se build for dado
        # No dev, aponta para a pasta src
        eel.init("web/src" if dev_mode else "web/dist", [".tsx", ".ts", ".jsx", ".js", ".html"])
        
        start_options = {
            "mode": "chrome",
            "host": "localhost",
            "port": 5000,
            "size": (1050, 700)
        }
        
        try:
            if dev_mode:
                # Se for dev, o Eel usa a porta 4000, mas pega a UI do Vite (5173)
                eel.start({"port": 5173}, **start_options)
            else:
                eel.start("index.html", **start_options)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop_peer()

    # Lógica de chamada no React

    def get_status(self) -> dict:
        """Retorna o estado atual para o front end ao carregar."""
        if not self.client:
            return {"running": False}
        
        return {
            "running": True,
            "name": self.client.name,
            "namespace": self.client.namespace,
            "port": self.client.listen_port,
            "ttl": self.client.ttl,
            "peers": self._get_peers_list()
        }

    def start_peer(self, config_data: dict) -> dict:
        """Inicia o P2PClient de forma não bloqueante para o Eel."""
        if self.client:
            return {"status": "ERROR", "message": "Peer já está rodando."}

        try:

            print("Iniciando peer com config:", config_data)

            self.config = {
                "name": config_data.get("name", ""),
                "namespace": config_data.get("namespace", ""),
                "listen_port": int(config_data.get("port", 4000)),
                "ttl": int(config_data.get("ttl", 3600)),
                "rendezvous_host": config_data.get("rdvHost", "127.0.0.1"),
                "rendezvous_port": int(config_data.get("rdvPort", 8080)),
                "ping_interval": 15,
                "ack_timeout": 5,
                "discover_interval": 30,
                "max_reconnect_attempts": 3,
                "log_level": "INFO"
            }

            self.client = P2PClient(self.config)
            self._hook_message_events()
            
            # Executa o start (que tem rede/sockets) no background
            def run_in_background():
                try:
                    self.client.start()
                    self._running = True
                    self._sync_thread = threading.Thread(target=self._ui_sync_loop, daemon=True)
                    self._sync_thread.start()
                    # Envia os logs informando sucesso no console visual!
                    import logging
                    logging.info("Peer iniciado no background!")
                except Exception as e:
                    import logging
                    logging.error(f"Erro na thread de inicio: {e}")

            threading.Thread(target=run_in_background, daemon=True).start()
            
            # Retorna IMEDIATAMENTE para a UI não travar
            return {"status": "OK", "peer": self.get_status()}
            
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def stop_peer(self) -> dict:
        """Para o P2PClient."""
        self._running = False
        if self.client:
            self.client.stop()
            self.client = None
        return {"status": "OK"}

    def discover_peers(self) -> dict:
        """Força o discovery."""
        if not self.client:
            return {"status": "ERROR", "message": "Cliente inativo."}
        try:
            self.client.discover_now(self.client.namespace)
            self._push_peers_update()
            return {"status": "OK"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def send_message(self, peer: dict, text: str) -> dict:
        """Envia SEND (unicast) para o destinatário."""
        if not self.client:
            return {"status": "ERROR", "message": "Cliente inativo."}
        
        peer_id = f"{peer['name']}@{peer['namespace']}"
        msg_id = self.client.router.send(peer_id, text)
        
        if msg_id:
            # Emite de volta para a UI registrar no chat
            msg_obj = {
                "id": msg_id,
                "direction": "out",
                "to": peer_id,
                "text": text,
                "timestamp": utc_timestamp()
            }
            eel.receiveEvent({"type": "MESSAGE_SENT", "message": msg_obj})()
            return {"status": "OK"}
        else:
            return {"status": "ERROR", "message": "Falha ao enviar (peer não conectado)."}

    def broadcast_message(self, scope: str, text: str) -> dict:
        """Envia PUB (broadcast) no namespace selecionado
        por scope."""
        if not self.client:
            return {"status": "ERROR"}
        
        msg_id = self.client.router.pub(scope, text)
        msg_obj = {
            "id": msg_id,
            "direction": "out",
            "to": f"Salas ({scope})",
            "text": text,
            "timestamp": utc_timestamp()
        }
        eel.receiveEvent({"type": "MESSAGE_SENT", "message": msg_obj})()
        return {"status": "OK", "sent": 1}

    # --- Helpers e Threads ---

    def _hook_message_events(self) -> None:
        """Modifica levemente os handlers do Router para avisar o Eel."""
        original_on_send = self.client.router.on_send
        original_on_pub = self.client.router.on_pub

        def hooked_on_send(conn, msg):
            original_on_send(conn, msg)
            eel.receiveEvent({
                "type": "MESSAGE_RECEIVED",
                "message": {
                    "id": msg.get("msg_id"),
                    "direction": "in",
                    "from": msg.get("src"),
                    "text": msg.get("payload"),
                    "timestamp": utc_timestamp()
                }
            })()

        def hooked_on_pub(conn, msg):
            original_on_pub(conn, msg)
            eel.receiveEvent({
                "type": "MESSAGE_RECEIVED",
                "message": {
                    "id": msg.get("msg_id"),
                    "direction": "in",
                    "from": f"{msg.get('src')} [BROADCAST]",
                    "text": msg.get("payload"),
                    "timestamp": utc_timestamp()
                }
            })()

        self.client.router.on_send = hooked_on_send
        self.client.router.on_pub = hooked_on_pub

    def _ui_sync_loop(self) -> None:
        """Thread que roda em background atualizando a tela do React."""
        while self._running and self.client:
            self._push_peers_update()
            time.sleep(3) # Sincroniza a cada 3 segundos

    def _push_peers_update(self) -> None:
        """Envia a lista consolidada de peers para a UI."""
        peers = self._get_peers_list()
        try:
            eel.receiveEvent({"type": "PEERS_UPDATED", "peers": peers})()
        except Exception:
            pass

    def _get_peers_list(self) -> list[dict]:
        """
        Retorna a lista consolidada de peers.
        """
        if not self.client: return []
        peers = []
        for entry in self.client.peer_table.all():
            # Filtra o próprio peer da lista da interface
            if entry.peer_id == self.client.peer_id: continue
            
            name, namespace = entry.peer_id.split("@", 1) if "@" in entry.peer_id else (entry.peer_id, "")
            peers.append({
                "name": name,
                "namespace": namespace,
                "ip": entry.ip,
                "port": entry.port,
                "state": entry.state.value
            })
        return peers


# --- Exposição das Rotas pro React (Wrappers) ---

@eel.expose
def get_status(): return _APP_INSTANCE.get_status()

@eel.expose
def start_peer(config):
    print(">>> [SUCESSO] O Eel recebeu a requisição do React!!") # Função de debug do Eel
    return _APP_INSTANCE.start_peer(config)

@eel.expose
def stop_peer(): return _APP_INSTANCE.stop_peer()

@eel.expose
def discover_peers(): return _APP_INSTANCE.discover_peers()

@eel.expose
def send_message(peer, text): return _APP_INSTANCE.send_message(peer, text)

@eel.expose
def broadcast_message(scope, text): return _APP_INSTANCE.broadcast_message(scope, text)