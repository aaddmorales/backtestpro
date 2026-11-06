@echo off
REM BotTested ORDEM 039 - leitor em MODO SOMBRA (nenhuma ordem)
cd /d %~dp0
start "BotTested O39 XAUUSD" cmd /k python bt_estrutura_sombra_o39.py --ativo XAUUSD --config config_execucao.json
start "BotTested O39 BTCUSD" cmd /k python bt_estrutura_sombra_o39.py --ativo BTCUSD --config config_execucao.json
