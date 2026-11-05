@echo off
REM BotTested experiencia ROMP-M15-0.1 XAUUSD (conta DEMO). Sem dimensionamento em config_romp.json as ordens ficam BLOQUEADAS.
cd /d %~dp0
if exist PARAR del PARAR
start "BotTested ROMP XAUUSD" cmd /k python bt_romp_m15_v001.py --config config_romp.json --pasta "%~dp0romp_XAUUSD"
