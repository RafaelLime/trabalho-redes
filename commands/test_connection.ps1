# Arquivo para testar conexão com o servidor em Windows PowerShell
# Não precisa de privilégios de administrador

# Recupera o arquivo salvo no config.json
$configJson = Get-Content -Path "./config.json" | ConvertFrom-Json

# Separa a informação de host e porta
$hostPort = $configJson.rendezvous_port
$hostIp = $configJson.rendezvous_host

# Teste para verificar se a porta e o endereço não estão vazios
Write-Host "Testando conexão com o servidor ${hostIp}:${hostPort}..."

# Faz o teste de conexão via Test-NetConnection, via TCP
$status = tnc -ComputerName $hostIp -Port $hostPort -InformationLevel Quiet

# Verifica se a conexão foi bem-sucedida
if ($status -eq $true) {
    Write-Host "O sevidor está aberto e escutando!"
    exit 0
} else {
    Write-Host "Falha de conexão com o servidor!"
    exit 1
}