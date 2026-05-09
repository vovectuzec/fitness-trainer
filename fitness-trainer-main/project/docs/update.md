# System Update Guide

## Підготовка до оновлення

Перед оновленням потрібно:
- створити резервну копію SQLite;
- зберегти конфігурації;
- перевірити сумісність Python.

## Backup

Створення резервної копії:

```bash
copy fitness_bot.db fitness_bot_backup.db