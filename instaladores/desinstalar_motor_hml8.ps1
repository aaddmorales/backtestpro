# desinstalar_motor_hml8.ps1 - C27R14 - desfaz o instalar_motor_hml8.ps1 (SOMENTE HOMOLOGACAO)
# 1) para o leitor do motor e remove o inicio automatico (pasta Inicializar);
# 2) restaura o Conector HOMOLOG anterior a partir do backup gravado na instalacao;
# 3) restaura BT_CV_ESPELHO / BT_CV_MOTOR_DIR anteriores (ou remove, se nao existiam);
# 4) BT_CV_SEGREDO so e removido com -RemoverSegredo (e so se nao existia antes da instalacao);
# 5) os dados do motor (barras, SAUDE, leitor.log) sao MOVIDOS para _desinstalado_<data>, nunca apagados.
# Nao toca em producao, no conector de producao nem no MT5.
# Uso: powershell -ExecutionPolicy Bypass -File .\instaladores\desinstalar_motor_hml8.ps1 [-RemoverSegredo] [-ReabrirConector]
param([string]$Destino = "C:\BotTested_HOMOLOG", [switch]$RemoverSegredo, [switch]$ReabrirConector)
$ErrorActionPreference = "Stop"
function Ok([string]$m) { Write-Host "OK  $m" -ForegroundColor Green }
$motorDst = Join-Path $Destino "motor"
$estadoArq = Join-Path $motorDst "instalacao_hml8.json"
$estado = $null
if (Test-Path -LiteralPath $estadoArq) { $estado = Get-Content -LiteralPath $estadoArq -Raw | ConvertFrom-Json }
else { Write-Host "aviso: $estadoArq ausente - restauro so o que for encontrado" -ForegroundColor Yellow }

# 1. parar leitor + inicio automatico
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*bt_motor_leitura_hml*" -or $_.CommandLine -like "*motor_iniciar.cmd*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$ini = if ($estado -and $estado.inicializar) { $estado.inicializar } else { Join-Path ([Environment]::GetFolderPath("Startup")) "BotTested_HOMOLOG_Motor.cmd" }
if (Test-Path -LiteralPath $ini) { Remove-Item -LiteralPath $ini -Force; Ok "inicio automatico removido ($ini)" } else { Ok "inicio automatico ja ausente" }
Ok "leitor do motor parado"

# 2. conector anterior
$jan = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*conector_homolog.py*" }
if ($jan) { $jan | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep 2 }
$bak = if ($estado) { $estado.backup_conector } else { $null }
if (-not $bak) { $bak = Get-ChildItem -LiteralPath $Destino -Directory -Filter "_backup_*" | Sort-Object Name | Select-Object -Last 1 | ForEach-Object { $_.FullName } }
if ($bak -and (Test-Path -LiteralPath $bak)) {
  foreach ($n in "conector_homolog.py", "conector_nucleo_homolog.py") {
    $o = Join-Path $bak $n
    if (Test-Path -LiteralPath $o) {
      Copy-Item -LiteralPath $o -Destination (Join-Path $Destino $n) -Force
      Ok ("restaurado {0} sha256 {1}" -f $n, (Get-FileHash -LiteralPath (Join-Path $Destino $n) -Algorithm SHA256).Hash.ToLower())
    }
  }
} else { Write-Host "aviso: nenhum backup do conector encontrado - conector hml8 mantido" -ForegroundColor Yellow }

# 3. variaveis
foreach ($v in "BT_CV_ESPELHO", "BT_CV_MOTOR_DIR") {
  $ant = if ($estado) { $estado.("${v}_anterior") } else { $null }
  [Environment]::SetEnvironmentVariable($v, $(if ($ant) { $ant } else { $null }), "User")
  Ok ("{0} {1}" -f $v, $(if ($ant) { "restaurada para $ant" } else { "removida" }))
}
if ($RemoverSegredo) {
  if ($estado -and $estado.BT_CV_SEGREDO_existia) { Write-Host "BT_CV_SEGREDO ja existia antes da instalacao - mantido" -ForegroundColor Yellow }
  else { [Environment]::SetEnvironmentVariable("BT_CV_SEGREDO", $null, "User"); Ok "BT_CV_SEGREDO removido do usuario" }
}

# 4. dados do motor preservados
if (Test-Path -LiteralPath $motorDst) {
  $arq = Join-Path $Destino ("_desinstalado_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
  Move-Item -LiteralPath $motorDst -Destination $arq
  Ok "motor e dados movidos para $arq (nada apagado)"
}
if ($ReabrirConector) {
  $py = (& py -c "import sys; print(sys.executable)")
  Start-Process $py -ArgumentList "`"$Destino\conector_homolog.py`"" -WorkingDirectory $Destino
  Ok "Conector HOMOLOG anterior reaberto"
}
Write-Host "Desinstalado. Feche e reabra o PowerShell para as variaveis de usuario valerem." -ForegroundColor Cyan
