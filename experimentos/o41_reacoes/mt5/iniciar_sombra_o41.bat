@echo off
REM BotTested ORDEM 041 - leitor em MODO SOMBRA: Referencia V1-200, Teste A e Teste B (nenhuma ordem)
cd /d %~dp0
start "BotTested O41 XAUUSD" cmd /k python bt_estrutura_sombra_o41.py --ativo XAUUSD --config config_execucao.json
start "BotTested O41 BTCUSD" cmd /k python bt_estrutura_sombra_o41.py --ativo BTCUSD --config config_execucao.json
