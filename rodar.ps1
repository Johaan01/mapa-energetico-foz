# Sobe o dashboard localmente e mostra como abrir no celular.
#
#   .\rodar.ps1            porta padrão 8765
#   .\rodar.ps1 -Porta 9000
#
# O python -m http.server já escuta em todas as interfaces, então o celular consegue
# acessar pelo IP da máquina na mesma rede wifi — útil para ensaiar a apresentação no
# aparelho de verdade, e não só no navegador do PC.

param([int]$Porta = 8765)

$web = Join-Path $PSScriptRoot "web"
if (-not (Test-Path (Join-Path $web "index.html"))) {
    Write-Error "Não achei web/index.html. Rode este script a partir da raiz do projeto."
    exit 1
}

# IP da máquina na rede local (ignora loopback e interfaces virtuais).
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and
                      $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL|Hyper-V" } |
       Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  Dashboard no ar" -ForegroundColor Green
Write-Host ""
Write-Host "    neste PC : " -NoNewline; Write-Host "http://localhost:$Porta" -ForegroundColor Cyan
if ($ip) {
    Write-Host "    no celular: " -NoNewline; Write-Host "http://${ip}:$Porta" -ForegroundColor Cyan
    Write-Host "                (celular precisa estar no mesmo wifi)"
}
Write-Host ""
Write-Host "    Ctrl+C para parar."
Write-Host ""

Start-Process "http://localhost:$Porta"
Set-Location $web
python -m http.server $Porta
