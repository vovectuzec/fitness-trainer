# Генерація документації

## Інструмент

Для автоматичної генерації документації у проєкті Fitness Trainer використовується Sphinx.

Sphinx дозволяє:
- автоматично створювати HTML-документацію;
- генерувати документацію з docstring;
- переглядати структуру проєкту;
- створювати веб-сайт документації.

---

# Встановлення

## Встановлення Sphinx


python -m pip install sphinx
Встановлення теми документації
python -m pip install sphinx-rtd-theme
Встановлення перевірки docstring
python -m pip install pydocstyle
Структура документації
docs/
├── source/
│   ├── conf.py
│   ├── index.rst
│   └── modules.rst
├── build/
└── generate_docs.md
Налаштування Sphinx
Ініціалізація документації
python -m sphinx.cmd.quickstart docs
Конфігурація conf.py

У файл docs/source/conf.py потрібно додати:

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

Підключення розширень:

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

Тема документації:

html_theme = "sphinx_rtd_theme"
Файл modules.rst
Модулі проєкту
==============

.. automodule:: project.fitness_telegram_bot
   :members:
   :undoc-members:
   :show-inheritance:
Генерація HTML-документації

Для генерації документації використовується команда:

python -m sphinx -b html docs/source docs/build/html
Результат генерації

Після виконання команди буде створено HTML-документацію у папці:

docs/build/html

Головний файл документації:

docs/build/html/index.html
Перевірка якості документації

Для перевірки docstring використовується pydocstyle:

python -m pydocstyle fitness_telegram_bot.py

Для документування функцій використовуються docstring.

Приклад:

def init_db():
    """
    Ініціалізує базу даних SQLite.

    Створює таблиці користувачів та прогресу.

    Returns:
        None
    """
Повторна генерація документації

Після будь-яких змін у коді документацію потрібно оновлювати:

python -m sphinx -b html docs/source docs/build/html
Інтеграція з Git

Після оновлення документації необхідно виконати:

git add .
git commit -m "Update project documentation"