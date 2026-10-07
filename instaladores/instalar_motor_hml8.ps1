# instalar_motor_hml8.ps1 - C27R14 rev.2 - SOMENTE HOMOLOGACAO / MT5 DEMO
# Instala o LEITOR DO MOTOR DOS CICLOS (motor congelado bt_ciclo_v1 2.4 + espelho do bt_vivo_sombra 7.4)
# e o Conector HOMOLOG v1.35-hml12 (ponte do motor + canal de comando) a partir DESTE repositorio (branch de ensaio), conferindo hashes completos.
# NAO contem segredo. O BT_CV_SEGREDO e digitado mascarado e conferido pela impressao publica da API homolog
# (/conector/cv-impressao) - o valor nunca e exibido, gravado em log nem enviado.
# Para em qualquer divergencia. Nao toca em main, producao, conector de producao nem conta real.
#
# Uso (PowerShell, na raiz do clone da branch ensaio/vitrine-c27r7-isolado):
#   powershell -ExecutionPolicy Bypass -File .\instaladores\instalar_motor_hml8.ps1 -Login <conta demo>
param(
  [Parameter(Mandatory = $true)][long]$Login,
  [string]$Ativo = "BTCUSD,XAUUSD",   # C27R24: um leitor por ativo, cada um na sua pasta (separe por virgula)
  [string]$Destino = "C:\BotTested_HOMOLOG",
  [string]$Repo = ""
)
# rev.4 (02/out): a funcao auxiliar chamava-se "Py" e o PowerShell (que nao diferencia maiusculas)
# resolvia "& py" para ela mesma -> recursao infinita (CallDepthOverflow). Agora chama py.exe por nome
# de aplicativo e aceita -Repo para rodar de fora do clone.
$ErrorActionPreference = "Stop"
$API_HML = "https://homolog-homolog.up.railway.app"
$MANIFESTO_SHA = "520bb812ee711caa60da6c7a1c8171b1e9b296b0ab174afbfbcb49488f834a2e"
$CONECTOR_SHA = @{
  "conector_homolog.py"        = "99801a024ee6bbc158a95be0792a804cc278632c5aa7d6e342626984e658131e"
  "conector_nucleo_homolog.py" = "801ac96e07c80fd34580ffca466605ebc5cdbe0b5f303fdf3a7b4712afb024ad"
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
Write-Host "=== Instalador motor dos Ciclos + Conector HOMOLOG hml12 ===" -ForegroundColor Cyan
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
Ok "conector hml12 conferido"

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
Ok "Conector HOMOLOG hml12 instalado em $Destino (anteriores em $bak)"
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
# C27R24: um leitor POR ATIVO, cada um em <dados>\<ATIVO>. O conector escolhe a pasta pelo simbolo do EA.
$ativos = @($Ativo -split "[,; ]+" | Where-Object { $_ } | ForEach-Object { $_.Trim().ToUpper() } | Select-Object -Unique)
if ($ativos.Count -lt 1) { Pare "nenhum ativo informado em -Ativo" }
foreach ($a in $ativos) { if ($a -notmatch '^[A-Z0-9._-]{3,20}$') { Pare "ativo invalido: $a" } }
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*bt_motor_leitura_hml*" -or $_.CommandLine -like "*motor_iniciar*.cmd*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
$startup = [Environment]::GetFolderPath("Startup")
$estado.inicializar = (Join-Path $startup "BotTested_HOMOLOG_Motor.cmd")
$estado.ativos = $ativos
$estado | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $motorDst "instalacao_hml8.json") -Encoding ASCII
$linhasIni = @("@echo off")
$t0 = Get-Date
foreach ($a in $ativos) {
  $dadosA = Join-Path $dados $a
  New-Item -ItemType Directory -Force -Path $dadosA | Out-Null
  $cmd = Join-Path $motorDst ("motor_iniciar_" + $a + ".cmd")
@"
@echo off
title BotTested HOMOLOG Motor $a (leitor dos Ciclos - so leitura)
:loop
"$py" "$motorDst\bt_motor_leitura_hml.py" --ativo $a --login $Login --terminal "$terminal" --dados "$dadosA" >> "$dadosA\leitor.log" 2>&1
ping -n 31 127.0.0.1 >nul
goto loop
"@ | Set-Content -LiteralPath $cmd -Encoding ASCII
  $linhasIni += "start `"BotTested HOMOLOG Motor $a`" /min cmd /c `"$cmd`""
  Start-Process cmd -ArgumentList "/c", "`"$cmd`"" -WindowStyle Minimized
  Start-Sleep 3
}
($linhasIni -join "`r`n") | Set-Content -LiteralPath (Join-Path $startup "BotTested_HOMOLOG_Motor.cmd") -Encoding ASCII
Ok "leitores iniciados: $($ativos -join ', ') (religam sozinhos; sobem com o Windows pela pasta Inicializar)"
foreach ($a in $ativos) {
  $dadosA = Join-Path $dados $a
  $sau = Join-Path $dadosA "SAUDE.json"
  while (((Get-Date) - $t0).TotalSeconds -lt 180) {
    if ((Test-Path -LiteralPath $sau) -and (Get-Item -LiteralPath $sau).LastWriteTime -gt $t0) { break }
    Start-Sleep 5
  }
  if (-not ((Test-Path -LiteralPath $sau) -and (Get-Item -LiteralPath $sau).LastWriteTime -gt $t0)) {
    Write-Host (Get-Content -LiteralPath (Join-Path $dadosA "leitor.log") -Tail 20 -ErrorAction SilentlyContinue | Out-String)
    Pare "o leitor de $a nao gravou SAUDE.json em 180 s (veja $dadosA\leitor.log acima). Se o simbolo nao existe com este nome na corretora, confira o nome exato no MT5."
  }
  $s = Get-Content -LiteralPath $sau -Raw | ConvertFrom-Json
  Write-Host ("SAUDE {7}: conta {0} {1} demo={2} fuso={3}s ({4}) ultima barra M15 (corretora) {5} erro={6}" -f $s.login, $s.servidor, $s.conta_demo, $s.off_corretora_s, $s.off_fonte, $s.ultima_barra_corretora, $s.erro_ultimo, $a)
  if (-not $s.conta_demo -or [long]$s.login -ne $Login) { Pare "leitor de $a nao esta na conta DEMO $Login" }
  if ($s.ativo -ne $a) { Pare "leitor na pasta de $a esta lendo $($s.ativo)" }
  if ($s.erro_ultimo) { Write-Host "aviso: leitor de $a com erro nesta passada: $($s.erro_ultimo) (mercado fechado nao e falha de instalacao; confira depois)" -ForegroundColor Yellow }
}

# 9. reabre o Conector HOMOLOG com o ambiente novo
Start-Process $py -ArgumentList "`"$Destino\conector_homolog.py`"", "--conectar" -WorkingDirectory $Destino
Ok "Conector HOMOLOG v1.35-hml12 aberto (conexao automatica se ja houver token salvo)"
Write-Host "Pronto. Os bots que ja estao nos graficos ($($ativos -join ', ')) da DEMO nao precisam ser reenviados: confira na janela do conector que eles conectaram." -ForegroundColor Cyan
Write-Host "Canal de comando (hml12): so funciona com a DEMO conferida (botao 'Conferir MT5 DEMO') e Algo Trading ligado no MT5 demo." -ForegroundColor Cyan
