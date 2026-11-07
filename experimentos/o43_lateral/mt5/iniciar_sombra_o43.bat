@echo off
REM BotTested ORDEM 043 - leitor em MODO SOMBRA: R0, R1 e R2 (posicoes virtuais, nenhuma ordem)
cd /d %~dp0
start "BotTested O43 XAUUSD" cmd /k python bt_lateral_sombra_o43.py --ativo XAUUSD --config config_execucao.json
start "BotTested O43 BTCUSD" cmd /k python bt_lateral_sombra_o43.py --ativo BTCUSD --config config_execucao.json
