# instalar_conector_hml18.ps1 - ORDEM 051 - SOMENTE HOMOLOGACAO / MT5 DEMO
# Atualiza o Conector HOMOLOG de v1.39-hml17 para v1.40-hml18 na MESMA pasta (C:\BotTested_HOMOLOG):
#   - conector_homolog.py e conector_nucleo_homolog.py (hml18) + ponte_lateral_hml18.py + pasta lateral\ (motor O48 sem alteracao)
#   - guarda os arquivos atuais em _backup_hml17_<data> (desfazer = copiar de volta)
#   - remove o inicio automatico do leitor separado da O48 (BotTestedLateralO48), se existir: ele nao e mais usado
# Nao contem segredo. Nao toca no motor, nas variaveis BT_CV_*, no EA, na producao nem no conector de producao.
# Uso (PowerShell, dentro da pasta extraida do pacote):
#   powershell -ExecutionPolicy Bypass -File .\instalar_conector_hml18.ps1
param([string]$Destino = "C:\BotTested_HOMOLOG")
$ErrorActionPreference = "Stop"
function Pare([string]$m) { Write-Host "PARADO: $m" -ForegroundColor Red; Write-Host "Nada mais foi alterado a partir deste ponto."; exit 1 }
function Ok([string]$m) { Write-Host "OK  $m" -ForegroundColor Green }
function Sha([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() }
$aqui = $PSScriptRoot
Write-Host "=== Conector HOMOLOG v1.40-hml18 (ORDEM 051) ===" -ForegroundColor Cyan

# 1. pacote integro
$man = Get-Content -LiteralPath (Join-Path $aqui "MANIFESTO_HML18.json") -Raw | ConvertFrom-Json
$arqs = @($man.PSObject.Properties | ForEach-Object { $_.Name })
foreach ($n in $arqs) {
  $p = Join-Path $aqui $n
  if (-not (Test-Path -LiteralPath $p)) { Pare "falta no pacote: $n" }
  if ((Sha $p) -ne $man.$n) { Pare "hash divergente no pacote: $n" }
}
Ok "pacote conferido ($($arqs.Count) arquivos)"

# 2. destino = instalacao atual da homologacao
if (-not (Test-Path -LiteralPath (Join-Path $Destino "conector_homolog.py"))) { Pare "nao achei $Destino\conector_homolog.py (instalacao HOMOLOG hml17)" }
$PYEXE = (Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $PYEXE) { Pare "py.exe nao encontrado (Python do python.org)" }
$eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$chk = & $PYEXE -c "import MetaTrader5, pandas, numpy, requests; print('ok')" 2>&1 | Out-String
$ErrorActionPreference = $eap
if ($chk.Trim() -ne "ok") { Pare "faltam pacotes Python. Rode: py -m pip install MetaTrader5 pandas numpy requests" }
Ok "Python com MetaTrader5, pandas, numpy e requests"

# 3. fecha o conector homolog aberto (o de producao nao e tocado)
$jan = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*conector_homolog.py*" }
if ($jan) { $jan | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 2; Ok "Conector HOMOLOG anterior fechado" }

# 4. backup + copia
$bak = Join-Path $Destino ("_backup_hml17_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $bak | Out-Null
foreach ($n in @("conector_homolog.py", "conector_nucleo_homolog.py", "ponte_lateral_hml18.py")) {
  $d = Join-Path $Destino $n
  if (Test-Path -LiteralPath $d) { Copy-Item -LiteralPath $d -Destination $bak }
}
if (Test-Path -LiteralPath (Join-Path $Destino "lateral")) { Copy-Item -LiteralPath (Join-Path $Destino "lateral") -Destination (Join-Path $bak "lateral") -Recurse }
New-Item -ItemType Directory -Force -Path (Join-Path $Destino "lateral") | Out-Null
foreach ($n in $arqs) {
  if ($n -notlike "*.py" -and $n -notlike "lateral/*") { continue }
  $d = Join-Path $Destino ($n -replace "/", "\")
  Copy-Item -LiteralPath (Join-Path $aqui ($n -replace "/", "\")) -Destination $d -Force
  if ((Sha $d) -ne $man.$n) { Pare "copia divergente: $d (restaure de $bak)" }
}
Ok "Conector HOMOLOG v1.40-hml18 copiado para $Destino (hml17 guardado em $bak)"

# 5. o leitor separado da O48 nao e mais usado: tira o inicio automatico dele, se existir
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $run -Name "BotTestedLateralO48" -ErrorAction SilentlyContinue) {
  Remove-ItemProperty -Path $run -Name "BotTestedLateralO48"; Ok "inicio automatico do leitor separado (O48) removido"
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*bt_lateral_leitor_o48.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Ok "leitor separado (O48) encerrado" }

# 6. abre o conector
Start-Process $PYEXE -ArgumentList "`"$Destino\conector_homolog.py`"", "--conectar" -WorkingDirectory $Destino
Ok "Conector HOMOLOG v1.40-hml18 aberto"
Write-Host "Proximo: no campo do token, deixe o token da campanha e acrescente, separado por espaco, o token lat_ gerado no cartao (passo 4 - Enviar). Depois: Parar/Conectar." -ForegroundColor Cyan
Write-Host "Desfazer: feche o conector e copie os arquivos de $bak de volta para $Destino." -ForegroundColor Cyan
