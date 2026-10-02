# instalar_motor_hml8.ps1 - C27R14 rev.2 - SOMENTE HOMOLOGACAO / MT5 DEMO
# Instala o LEITOR DO MOTOR DOS CICLOS (motor congelado bt_ciclo_v1 2.4 + espelho do bt_vivo_sombra 7.4)
# e o Conector HOMOLOG v1.35-hml8 a partir DESTE repositorio (branch de ensaio), conferindo hashes completos.
# NAO contem segredo. O BT_CV_SEGREDO e digitado mascarado e conferido pela impressao publica da API homolog
# (/conector/cv-impressao) - o valor nunca e exibido, gravado em log nem enviado.
# Para em qualquer divergencia. Nao toca em main, producao, conector de producao nem conta real.
#
# Uso (PowerShell, na raiz do clone da branch ensaio/vitrine-c27r7-isolado):
#   powershell -ExecutionPolicy Bypass -File .\instaladores\instalar_motor_hml8.ps1 -Login <conta demo>
param(
  [Parameter(Mandatory = $true)][long]$Login,
  [string]$Ativo = "XAUUSD",
  [string]$Destino = "C:\BotTested_HOMOLOG",
  [string]$Repo = ""
)
# rev.4 (02/out): a funcao auxiliar chamava-se "Py" e o PowerShell (que nao diferencia maiusculas)
# resolvia "& py" para ela mesma -> recursao infinita (CallDepthOverflow). Agora chama py.exe por nome
# de aplicativo e aceita -Repo para rodar de fora do clone.
$ErrorActionPreference = "Stop"
$API_HML = "https://homolog-homolog.up.railway.app"
$MANIFESTO_SHA = "13fad574fd4010fabeb6e978972120780a2bd1ce0e64f6cc66ead07420006603"
$CONECTOR_SHA = @{
  "conector_homolog.py"        = "44d426187e9b65a1816949ed267c08bd8c6598cf64280d5582c511e0d7aee83b"
  "conector_nucleo_homolog.py" = "fc6ffe292ec8408629b67ea0abd23e3ca722e80f3fd270c5aaaf5a585f5c5018"
}
function Pare([string]$m) { Write-Host "PARADO: $m" -ForegroundColor Red; Write-Host "Nada mais foi alterado a partir deste ponto."; exit 1 }
function Ok([string]$m) { Write-Host "OK  $m" -ForegroundColor Green }
function Sha([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() }
$PYEXE = (Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
function RodarPython([string]$codigo) {   # chamada nativa sem transformar stderr em erro do PowerShell 5.1
  $eap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  try { $o = & $PYEXE -c $codigo 2>&1 | Out-String; return @($LASTEXITCODE, $o.Trim()) } finally { $ErrorActionPreference = $eap }
}

if (-not $Repo) { $Repo = Join-Path $PSScriptRoot ".." }
$repo = (Resolve-Path $Repo).Path
if (-not (Test-Path -LiteralPath (Join-Path $repo "motor_ciclos\MANIFESTO_MOTOR.sha256"))) { Pare "motor_ciclos nao encontrado em $repo (use -Repo <pasta do clone>)" }
$motorSrc = Join-Path $repo "motor_ciclos"
$conSrc = Join-Path $repo "conector_homolog\hml"
Write-Host "=== Instalador motor dos Ciclos + Conector HOMOLOG hml8 ===" -ForegroundColor Cyan
Write-Host "repositorio: $repo"

# 1. repositorio limpo e na branch de ensaio
Push-Location $repo
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
$commit = (git rev-parse HEAD).Trim()
if ($branch -ne "ensaio/vitrine-c27r7-isolado") { Pop-Location; Pare "branch atual '$branch' (esperado ensaio/vitrine-c27r7-isolado)" }
$sujo = git status --porcelain -- motor_ciclos conector_homolog instaladores
if ($sujo) { Pop-Location; Pare "arquivos alterados localmente em motor_ciclos/conector_homolog/instaladores:`n$sujo" }
Pop-Location
Ok "branch $branch commit $commit"

# 2. manifesto do motor e cada arquivo listado
$man = Join-Path $motorSrc "MANIFESTO_MOTOR.sha256"
if ((Sha $man) -ne $MANIFESTO_SHA) { Pare "MANIFESTO_MOTOR.sha256 diverge do esperado ($MANIFESTO_SHA)" }
$lista = @{}
foreach ($l in Get-Content -LiteralPath $man) {
  if ($l -match '^([0-9a-f]{64})  (.+)$') { $lista[$Matches[2]] = $Matches[1] }
}
foreach ($k in $lista.Keys) {
  $p = Join-Path $motorSrc ($k -replace '/', '\')
  if (-not (Test-Path -LiteralPath $p)) { Pare "faltando no repositorio: motor_ciclos\$k" }
  if ((Sha $p) -ne $lista[$k]) { Pare "hash divergente: motor_ciclos\$k" }
}
Ok "manifesto do motor: $($lista.Count) arquivos conferidos (bt_ciclo_v1 9ac1af94..., bt_vivo_sombra 47a2ade7...)"
foreach ($n in $CONECTOR_SHA.Keys) {
  if ((Sha (Join-Path $conSrc $n)) -ne $CONECTOR_SHA[$n]) { Pare "hash divergente: conector_homolog\hml\$n" }
}
Ok "conector hml8 conferido"

# 3. seguranca: nada executando ordens por fora da plataforma
$procs = Get-CimInstance Win32_Process
$exec = $procs | Where-Object { $_.CommandLine -like "*bt_vivo_sombra*" -and $_.CommandLine -like "*--executa*" }
if ($exec) { Pare "bt_vivo_sombra esta rodando com --executa (pid $($exec.ProcessId -join ',')). Encerre-o: ele envia ordens por conta propria." }
$sombra = $procs | Where-Object { $_.CommandLine -like "*bt_vivo_sombra*" }
if ($sombra) { Write-Host "aviso: bt_vivo_sombra (sombra, sem --executa) rodando - nao interfere; o leitor usa pasta propria" -ForegroundColor Yellow }

# 4. Python e bibliotecas
if (-not $PYEXE) { Pare "Python launcher (py.exe) nao encontrado" }
$r = RodarPython "import sys; print(sys.executable)"; $py = $r[1]
if ($r[0] -ne 0 -or -not (Test-Path -LiteralPath $py)) { Pare "Python nao respondeu: $($r[1])" }
$r = RodarPython "import sys; assert sys.version_info >= (3, 10), sys.version"
if ($r[0] -ne 0) { Pare "Python >= 3.10 necessario ($($r[1]))" }
$r = RodarPython "import pandas, numpy, MetaTrader5"
if ($r[0] -ne 0) { Pare "faltam bibliotecas. Rode: py -m pip install --user -r `"$motorSrc\requirements_motor.txt`" e rode este instalador de novo." }
Ok "Python $py com pandas/numpy/MetaTrader5"

# 5. instalacao MT5 DEMO = a mesma fixada no Conector HOMOLOG
$cfg = Join-Path $HOME "BotTested_Conector_HOMOLOG_config.json"
if (-not (Test-Path -LiteralPath $cfg)) { Pare "Conector HOMOLOG sem configuracao ($cfg) - abra-o e fixe a instalacao DEMO" }
$pin = (Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json).mt5_pin
if (-not $pin) { Pare "Conector HOMOLOG sem instalacao MT5 fixada (mt5_pin)" }
$dataDir = Split-Path -Parent $pin
$origem = Join-Path $dataDir "origin.txt"
if (-not (Test-Path -LiteralPath $origem)) { Pare "origin.txt ausente em $dataDir - nao sei qual terminal64.exe e desta pasta" }
$instDir = (Get-Content -LiteralPath $origem -Raw -Encoding Unicode).Trim()
if (-not (Test-Path -LiteralPath (Join-Path $instDir "terminal64.exe"))) { $instDir = (Get-Content -LiteralPath $origem -Raw).Trim() }
$terminal = Join-Path $instDir "terminal64.exe"
if (-not (Test-Path -LiteralPath $terminal)) { Pare "terminal64.exe nao encontrado em $instDir" }
Ok "MT5 DEMO fixado: $terminal (dados $dataDir)"

# 6. copia com conferencia (antes: registra o estado anterior para o desinstalador restaurar)
$estado = [ordered]@{
  instalado_em = (Get-Date).ToString("s"); commit = $commit; destino = $Destino
  BT_CV_ESPELHO_anterior = [Environment]::GetEnvironmentVariable("BT_CV_ESPELHO", "User")
  BT_CV_MOTOR_DIR_anterior = [Environment]::GetEnvironmentVariable("BT_CV_MOTOR_DIR", "User")
  BT_CV_SEGREDO_existia = [bool][Environment]::GetEnvironmentVariable("BT_CV_SEGREDO", "User")
  backup_conector = $null; inicializar = $null
}
$motorDst = Join-Path $Destino "motor"
$dados = Join-Path $motorDst "dados"
New-Item -ItemType Directory -Force -Path $motorDst, $dados | Out-Null
$copiar = $lista.Keys | Where-Object { $_ -like "*.py" -and $_ -notlike "testes/*" -and $_ -notlike "referencia_27set/*" }
foreach ($k in $copiar) {
  Copy-Item -LiteralPath (Join-Path $motorSrc $k) -Destination (Join-Path $motorDst $k) -Force
  if ((Sha (Join-Path $motorDst $k)) -ne $lista[$k]) { Pare "copia divergente: $motorDst\$k" }
}
Ok "motor instalado em $motorDst ($(@($copiar).Count) modulos)"
$jan = $procs | Where-Object { $_.CommandLine -like "*conector_homolog.py*" }
if ($jan) { $jan | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 2 }
$bak = Join-Path $Destino ("_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
$estado.backup_conector = $bak
New-Item -ItemType Directory -Force -Path $bak | Out-Null
foreach ($n in $CONECTOR_SHA.Keys) {
  $d = Join-Path $Destino $n
  if (Test-Path -LiteralPath $d) { Copy-Item -LiteralPath $d -Destination $bak }
  Copy-Item -LiteralPath (Join-Path $conSrc $n) -Destination $d -Force
  if ((Sha $d) -ne $CONECTOR_SHA[$n]) { Pare "copia divergente: $d" }
}
Ok "Conector HOMOLOG hml8 instalado em $Destino (anteriores em $bak)"
$estado | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $motorDst "instalacao_hml8.json") -Encoding ASCII

# 7. segredo: conferido pela impressao da API homolog, sem exibir
function Impressao([string]$s) {
  $b = [Text.Encoding]::UTF8.GetBytes("bt-cv-impressao-v1|" + $s)
  $h = [Security.Cryptography.SHA256]::Create().ComputeHash($b)
  (($h | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 16)
}
$api = Invoke-RestMethod -Uri "$API_HML/conector/cv-impressao" -TimeoutSec 30
if (-not $api.configurado) { Pare "a API homolog ainda nao tem BT_CV_SEGREDO (deploy pendente?)" }
$seg = [Environment]::GetEnvironmentVariable("BT_CV_SEGREDO", "User")
if ($seg -and (Impressao $seg) -eq $api.impressao) {
  Ok "BT_CV_SEGREDO do usuario confere com a API homolog (impressao $($api.impressao))"
} else {
  Write-Host "Cole o BT_CV_SEGREDO do Railway homolog (servico bottested-homolog > Variables). Nada aparece na tela." -ForegroundColor Cyan
  $sec = Read-Host -AsSecureString "BT_CV_SEGREDO"
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try { $seg = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  if ((Impressao $seg) -ne $api.impressao) { $seg = $null; Pare "segredo digitado NAO confere com a API homolog - nada gravado" }
  [Environment]::SetEnvironmentVariable("BT_CV_SEGREDO", $seg, "User")
  Ok "BT_CV_SEGREDO gravado no usuario (confere com a API homolog; valor nao exibido)"
}
$env:BT_CV_SEGREDO = $seg; $seg = $null
[Environment]::SetEnvironmentVariable("BT_CV_ESPELHO", $dados, "User"); $env:BT_CV_ESPELHO = $dados
[Environment]::SetEnvironmentVariable("BT_CV_MOTOR_DIR", $motorDst, "User"); $env:BT_CV_MOTOR_DIR = $motorDst
Ok "BT_CV_ESPELHO=$dados  BT_CV_MOTOR_DIR=$motorDst"

# 8. leitor do motor: inicio, religamento e inicializacao com o Windows
$cmd = Join-Path $motorDst "motor_iniciar.cmd"
@"
@echo off
title BotTested HOMOLOG Motor (leitor dos Ciclos - so leitura)
:loop
"$py" "$motorDst\bt_motor_leitura_hml.py" --ativo $Ativo --login $Login --terminal "$terminal" --dados "$dados" >> "$dados\leitor.log" 2>&1
ping -n 31 127.0.0.1 >nul
goto loop
"@ | Set-Content -LiteralPath $cmd -Encoding ASCII
$startup = [Environment]::GetFolderPath("Startup")
$estado.inicializar = (Join-Path $startup "BotTested_HOMOLOG_Motor.cmd")
$estado | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $motorDst "instalacao_hml8.json") -Encoding ASCII
"@echo off`r`nstart `"BotTested HOMOLOG Motor`" /min cmd /c `"$cmd`"" | Set-Content -LiteralPath (Join-Path $startup "BotTested_HOMOLOG_Motor.cmd") -Encoding ASCII
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*bt_motor_leitura_hml*" -or $_.CommandLine -like "*motor_iniciar.cmd*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$t0 = Get-Date
Start-Process cmd -ArgumentList "/c", "`"$cmd`"" -WindowStyle Minimized
Ok "leitor iniciado (religa sozinho; sobe com o Windows pela pasta Inicializar)"
$sau = Join-Path $dados "SAUDE.json"
while (((Get-Date) - $t0).TotalSeconds -lt 120) {
  Start-Sleep 5
  if ((Test-Path -LiteralPath $sau) -and (Get-Item -LiteralPath $sau).LastWriteTime -gt $t0) { break }
}
if (-not ((Test-Path -LiteralPath $sau) -and (Get-Item -LiteralPath $sau).LastWriteTime -gt $t0)) {
  Write-Host (Get-Content -LiteralPath (Join-Path $dados "leitor.log") -Tail 20 -ErrorAction SilentlyContinue | Out-String)
  Pare "o leitor nao gravou SAUDE.json em 120 s (veja $dados\leitor.log acima)"
}
$s = Get-Content -LiteralPath $sau -Raw | ConvertFrom-Json
Write-Host ("SAUDE: conta {0} {1} demo={2} fuso={3}s ({4}) ultima barra M15 (corretora) {5} erro={6}" -f $s.login, $s.servidor, $s.conta_demo, $s.off_corretora_s, $s.off_fonte, $s.ultima_barra_corretora, $s.erro_ultimo)
if (-not $s.conta_demo -or [long]$s.login -ne $Login) { Pare "leitor nao esta na conta DEMO $Login" }
if ($s.erro_ultimo) { Pare "leitor com erro: $($s.erro_ultimo)" }

# 9. reabre o Conector HOMOLOG com o ambiente novo
Start-Process $py -ArgumentList "`"$Destino\conector_homolog.py`"" -WorkingDirectory $Destino
Ok "Conector HOMOLOG v1.35-hml8 aberto"
Write-Host "Pronto. Proximo passo: Vitrine > MASTER > ... > Enviar para o MT5 (nome novo) e anexar ao $Ativo M15 da DEMO." -ForegroundColor Cyan
