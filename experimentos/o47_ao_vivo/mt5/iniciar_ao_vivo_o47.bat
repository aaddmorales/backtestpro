@echo off
REM BotTested ORDEM 047 - leitor AO VIVO em MODO SOMBRA: M15, M30 e H1 por tick (posicoes virtuais, nenhuma ordem)
REM INICIO congelado: 00:00 do servidor da 1a segunda-feira apos a verificacao da instalacao. Ajuste a data abaixo se instalar depois dela.
set INICIO=2026-11-09
cd /d %~dp0
start "BotTested O47 XAUUSD" cmd /k python bt_ao_vivo_o47.py --ativo XAUUSD --inicio %INICIO% --config config_execucao.json
start "BotTested O47 BTCUSD" cmd /k python bt_ao_vivo_o47.py --ativo BTCUSD --inicio %INICIO% --config config_execucao.json
