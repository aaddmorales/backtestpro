@echo off
REM BotTested ORDEM 042 - leitor em MODO SOMBRA: Ref, E, S e E+S (posicoes virtuais, nenhuma ordem)
cd /d %~dp0
start "BotTested O42 XAUUSD" cmd /k python bt_estrutura_sombra_o42.py --ativo XAUUSD --config config_execucao.json
start "BotTested O42 BTCUSD" cmd /k python bt_estrutura_sombra_o42.py --ativo BTCUSD --config config_execucao.json
