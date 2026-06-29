# Ponto de entrada ajustado para iniciar a Interface Gráfica

'''
Para fazer a execução do gui, primeiro execute o comando em ./web:
    npm run dev
Depois de realizar esse comando, agora pode executar o backend com:
    python gui.py
'''

import gevent.monkey
gevent.monkey.patch_all()

import sys
import logging
from app import P2PGUIApp

def main() -> int:
    # Configuração básica de log (o app.py vai interceptar depois para jogar na UI)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    print("Iniciando Aplicação P2P (Modo Gráfico)...")
    
    app = P2PGUIApp()
    
    # Se você for rodar usando npm run dev (vite), deixe dev_mode=True
    # Se for gerar o build final (HTML/JS na pasta), mude para False.
    app.start_ui(dev_mode=True)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())