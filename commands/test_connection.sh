#!/bin/bash
# Script para teste de conexão com o servidor no Linux
# Precisa ter instalado o NetCat e o jq
# Executa no terminal: sudo apt-get install netcat jq

# Recupera a porta e o endereço do servidor salvo em config.json
porta=$(jq -r '.rendezvous_port' ./config.json)
host=$(jq -r '.rendezvous_host' ./config.json)

# Verifica se a porta e o endereço estão vazios
echo "Testando a conexão com o servidor $host:$porta ..."

# Faz o teste de conexão via NetCat em TCP
nc -zv $host $porta

# Retorna se a conxão foi bem-sucedida ou não
if [ $? -eq 0 ]; then

    echo "Conexão com o servidor bem sucedida!"

else

    echo "Falha na conexão com o servidor!"

fi