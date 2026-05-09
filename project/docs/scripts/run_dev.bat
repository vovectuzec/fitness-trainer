@echo off

echo Starting Fitness Trainer in DEV mode...

cd /d %~dp0\..\..

python fitness_telegram_bot.py

pause