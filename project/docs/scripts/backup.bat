@echo off

echo Creating backup...

cd /d %~dp0\..\..

if not exist backup mkdir backup

if exist fitness_bot.db (
    copy fitness_bot.db backup\fitness_bot_backup.db
    echo Backup completed.
) else (
    echo Database file not found.
)

pause