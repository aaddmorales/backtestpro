@echo off
REM BotTested ORDEM 040 - leitor em MODO SOMBRA: V0, V1 e V1-200 (nenhuma ordem)
cd /d %~dp0
start "BotTested O40 XAUUSD" cmd /k python bt_estrutura_sombra_o40.py --ativo XAUUSD --config config_execucao.json
start "BotTested O40 BTCUSD" cmd /k python bt_estrutura_sombra_o40.py --ativo BTCUSD --config config_execucao.json
