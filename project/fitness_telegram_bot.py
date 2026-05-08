import os
import re
import sqlite3
import logging
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler
)

import matplotlib.pyplot as plt
from io import BytesIO
import pandas as pd

# ---------- Конфігурація ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'fitness_bot.db'
BOT_TOKEN = '8225179024:AAHFSVd0EMF1hJRDDzbd2vp8b0QJ--j2V1g'  # залишив твій токен як у вихідному коді

# ---------- Ініціалізація БД ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Користувачі
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT, name TEXT, age INTEGER, sex TEXT,
        height_cm REAL, weight_kg REAL, goal TEXT, created_at TEXT
    )''')

    # Вправи: підтримуємо схему з muscle_group
    cur.execute('''CREATE TABLE IF NOT EXISTS exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        muscle_group TEXT,
        muscles TEXT,
        description TEXT,
        demo_url TEXT
    )''')

    # Додаємо таблиці для відстеження прогресу
    cur.execute('''CREATE TABLE IF NOT EXISTS weight_progress (
        user_id INTEGER,
        date TEXT,
        weight REAL,
        notes TEXT,
        PRIMARY KEY (user_id, date)
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS workout_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        exercise TEXT,
        sets INTEGER,
        reps INTEGER,
        weight REAL,
        notes TEXT
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS measurement_progress (
        user_id INTEGER,
        date TEXT,
        chest REAL,
        waist REAL,
        hips REAL,
        biceps REAL,
        thighs REAL,
        notes TEXT,
        PRIMARY KEY (user_id, date)
    )''')
    
    conn.commit()
    conn.close()

def table_has_column(conn, table, column):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def seed_exercises():
    """
    Заповнює таблицю exercises, якщо вона порожня.
    Додає набір вправ розподілених по muscle_group.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exercises")
    count = cur.fetchone()[0]
    if count > 0:
        # Очищаємо існуючі вправи для оновлення
        cur.execute("DELETE FROM exercises")
        conn.commit()

    # Формуємо список вправ: (name, group, muscles, description, url)
    exercises = [
        # Ноги
        ("Присідання зі штангою", "Ноги", "Квадрицепс, сідниці, стегна",
         "Штанга на плечах, опускайтесь до рівня паралелі стегон з підлогою, піднімайтесь, тримайте спину рівною.",
         "https://www.youtube.com/watch?v=aclHkVaku9U"),
        ("Присідання з власною вагою", "Ноги", "Квадрицепс, сідниці",
         "Ноги на ширині плечей, зберігайте корпус прямо, опускайтесь і піднімайтесь контрольовано.",
         "https://www.youtube.com/watch?v=aclHkVaku9U"),
        ("Випади вперед", "Ноги", "Квадрицепс, сідниці",
         "Крок вперед, опускайтесь до кута 90° в коліні, повертайтесь у стартову позицію.",
         "https://www.youtube.com/watch?v=QOVaHwm-Q6U"),
        ("Сідничний міст", "Ноги", "Сідниці, задня поверхня стегна",
         "Ляжте на спину, ноги зігнуті, піднімайте таз, напруження в сідницях.",
         "https://www.youtube.com/watch?v=8bbE64NuDTU"),

        # Груди
        ("Віджимання вузьким хватом", "Груди", "Груди, трицепс",
         "Руки трохи ближче ширини плечей, опускайтесь, тримайте корпус рівним.",
         "https://www.youtube.com/watch?v=IODxDxX7oi4"),
        ("Жим лежачи", "Груди", "Грудні м'язи, трицепс, плечі",
         "Ляжте на лавку, опускайте штангу до грудей, витискайте вгору контрольовано.",
         "https://www.youtube.com/watch?v=rT7DgCr-3pg"),
        ("Розведення гантелей", "Груди", "Грудні м'язи",
         "Ляжте на лавку, розведення гантелей у сторони і зведення над грудьми.",
         "https://www.youtube.com/watch?v=eozdVDA78K0"),
        ("Пуловер з гантелею", "Груди", "Грудні м'язи, широчайші",
         "Лежачи на лавці, опускайте гантелю за голову, розтягуючи грудні м'язи, потім піднімайте назад.",
         "https://www.youtube.com/watch?v=5YStMv6m2g8"),
        ("Кросовер зверху вниз", "Груди", "Нижня частина грудних м'язів",
         "Стоячи між блоками, руки підняті, зведіть їх вниз і всередину перед собою.",
         "https://www.youtube.com/watch?v=taI4XduLpTk"),
        ("Віджимання з широкою постановкою", "Груди", "Грудні м'язи, передня дельта",
         "Прийміть упор лежачи з руками ширше плечей, опускайтесь до торкання грудьми підлоги.",
         "https://www.youtube.com/watch?v=oQoPQy8IyMM"),

        # Спина
        ("Тяга штанги в нахилі", "Спина", "Широчайші, ромбоподібні, нижня частина спини",
         "Нахил корпусу ~45°, тягніть штангу до живота, тримайте спину рівною.",
         "https://www.youtube.com/watch?v=GZbfZ033f74"),
        ("Підтягування", "Спина", "Широчайші, біцепс",
         "Візьміться широким хватом і підтягніться до підборіддя вище перекладини.",
         "https://www.youtube.com/watch?v=eGo4IYlbE5g"),
        ("Тяга горизонтального блоку", "Спина", "Середня частина спини, широчайші",
         "Сидячи тягніть рукоятку до живота, зводячи лопатки.", "https://www.youtube.com/watch?v=vT2GjY_Umpw"),
        ("Тяга Т-грифа", "Спина", "Широчайші, середня частина спини",
         "Стоячи над Т-грифом, тягніть його до живота, зводячи лопатки.",
         "https://www.youtube.com/watch?v=j3Igk5nyZE4"),
        ("Пулл-овер лежачи", "Спина", "Широчайші, зубчасті м'язи",
         "Лежачи на лавці, опускайте штангу за голову і повертайте назад.",
         "https://www.youtube.com/watch?v=geen0jmiDB8"),
        ("Шраги зі штангою", "Спина", "Трапеції, верх спини",
         "Тримаючи штангу в опущених руках, піднімайте плечі вгору.",
         "https://www.youtube.com/watch?v=cJRVVxmytaM"),

        # Плечі
        ("Жим штанги сидячи", "Плечі", "Дельти, трапеції",
         "Сидячи, витискайте штангу вгору від плечей.", "https://www.youtube.com/watch?v=qEwKCR5JCog"),
        ("Підйом гантелей у сторони", "Плечі", "Середня дельта",
         "Руки злегка зігнуті, піднімайте гантелі у сторони до рівня плечей.", "https://www.youtube.com/watch?v=3VcKaXpzqRo"),
        ("Тяга до підборіддя", "Плечі", "Передня/середня дельти, трапеції",
         "Тягніть штангу біля стегна вгору до підборіддя, лікті вгору.", "https://www.youtube.com/watch?v=3D7f8dB0pHc"),
        ("Жим гантелей сидячи", "Плечі", "Дельтоподібні м'язи",
         "Сидячи, витискайте гантелі вгору від рівня плечей.",
         "https://www.youtube.com/watch?v=qEwKCR5JCog"),
        ("Розведення в нахилі", "Плечі", "Задня дельта",
         "У нахилі, піднімайте гантелі у сторони до рівня плечей.",
         "https://www.youtube.com/watch?v=ttvfGg9d76c"),
        ("Протяжка штанги", "Плечі", "Дельти, трапеції",
         "Тягніть штангу вгору вздовж тіла до рівня підборіддя.",
         "https://www.youtube.com/watch?v=hxBZso6o9k0"),

        # Біцепс
        ("Підйом штанги на біцепс", "Біцепс", "Біцепс",
         "Стоячи, піднімайте штангу контрольовано, лікті не рухаються.", "https://www.youtube.com/watch?v=kwG2ipFRgfo"),
        ("Молоткові згинання", "Біцепс", "Брахіаліс, біцепс",
         "Тримайте гантелі нейтральним хватом і згинайте лікоть.", "https://www.youtube.com/watch?v=zC3nLlEvin4"),
        ("Згинання на лавці Скотта з гантелями", "Біцепс", "Біцепс",
         "Спираючись на лавку Скотта, виконуйте згинання рук з гантелями.",
         "https://www.youtube.com/watch?v=9ru7FzrJt5M"),
        ("Зворотні згинання зі штангою", "Біцепс", "Брахіаліс, біцепс",
         "Хватом знизу виконуйте згинання рук зі штангою.",
         "https://www.youtube.com/watch?v=nRgxYX2Ve9w"),
        ("Павукові згинання", "Біцепс", "Біцепс, брахіаліс",
         "На похилій лавці виконуйте почергові згинання рук з гантелями.",
         "https://www.youtube.com/watch?v=QZEqB6wUPxQ"),

        # Трицепс
        ("Французький жим", "Трицепс", "Трицепс",
         "У положенні лежачи опускайте гриф до лоба/за голову і витискайте вгору.", "https://www.youtube.com/watch?v=GCa8K8nN6K0"),
        ("Віджимання на брусах", "Трицепс", "Трицепс, груди",
         "Нахиляйтесь вперед або тримайтесь прямо для зміщення навантаження.", "https://www.youtube.com/watch?v=6kALZikXxLc"),
        ("Розгинання з канатом", "Трицепс", "Трицепс",
         "На верхньому блоці з канатною рукояттю виконуйте розгинання рук вниз.",
         "https://www.youtube.com/watch?v=kiuVA0gs3EI"),
        ("Жим вузьким хватом", "Трицепс", "Трицепс, передня дельта",
         "Лежачи на лавці, виконуйте жим штанги вузьким хватом.",
         "https://www.youtube.com/watch?v=b8UGX2zK09Y"),
        ("Розгинання в нахилі", "Трицепс", "Трицепс",
         "У нахилі з гантелею за головою виконуйте розгинання руки.",
         "https://www.youtube.com/watch?v=_gsUck-7M74"),

        # Передпліччя
        ("Звиток зап'ястками зі штангою", "Передпліччя", "Передпліччя",
         "Сидячи, кисті на грифі, виконуйте прокручування/звиток.", "https://www.youtube.com/watch?v=1xMaFsRZgR8"),
        ("Згинання зап'ясть на лавці", "Передпліччя", "Передпліччя (згиначі)",
         "Спираючись передпліччями на лавку, виконуйте згинання зап'ясть.",
         "https://www.youtube.com/watch?v=qG7Kz8FWwmE"),
        ("Зворотні згинання на лавці", "Передпліччя", "Передпліччя (розгиначі)",
         "Спираючись передпліччями на лавку, виконуйте розгинання зап'ясть.",
         "https://www.youtube.com/watch?v=RXST6Z0qXzY"),
        ("Утримання диска", "Передпліччя", "Передпліччя, хват",
         "Утримуйте диск від штанги пальцями, стоячи з опущеними руками.",
         "https://www.youtube.com/watch?v=2qGT8JtKI1Q"),

        # Сідниці (також можна в Ноги, але виділимо окремо)
        ("Болгарські випади", "Сідниці", "Сідниці, квадрицепс",
         "Задня нога на лавці, робіть випади вперед для сильної опрацювання сідниць.",
         "https://www.youtube.com/watch?v=2C-uNgKwPLE"),
        ("Румунська тяга", "Сідниці", "Сідниці, задня поверхня стегна",
         "Злегка зігнуті коліна, нахил корпусу і рух через сідниці.", "https://www.youtube.com/watch?v=2SHsk9AzdjA"),
        ("Присідання сумо", "Сідниці", "Сідниці, внутрішня частина стегна",
         "Широка постановка ніг, присідайте, тримаючи корпус прямо.",
         "https://www.youtube.com/watch?v=9ZuXKqRbT9k"),
        ("Сідничний місток з вагою", "Сідниці", "Сідниці, задня поверхня стегна",
         "Лежачи на спині з вагою на стегнах, піднімайте таз вгору.",
         "https://www.youtube.com/watch?v=vQgM5TlPDIk"),
        ("Степ-ups на лавку", "Сідниці", "Сідниці, квадрицепс",
         "По черзі піднімайтесь на лавку, тримаючи корпус прямо.",
         "https://www.youtube.com/watch?v=WCFCdxzFBa4")
    ]

    cur.executemany('''
        INSERT INTO exercises (name, muscle_group, muscles, description, demo_url)
        VALUES (?, ?, ?, ?, ?)
    ''', exercises)

    conn.commit()
    conn.close()

# ---------- Планувальник нагадувань ----------
scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Kiev'))
scheduler.start()

# Глобальна змінна для bot
bot_instance = None

def escape_markdown(text):
    """Екранує спеціальні символи для Markdown V2"""
    if not text:
        return text
    # Символи, які потрібно екранувати в Markdown V2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def schedule_reminder(user_id: int, when: datetime, text: str):
    def job():
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def send_reminder():
                await bot_instance.send_message(chat_id=user_id, text=f"🔔 Нагадування: {text}")
                logger.info(f"Надіслано нагадування користувачу {user_id}: {text}")
            
            loop.run_until_complete(send_reminder())
            loop.close()
        except Exception as e:
            logger.error(f"Помилка відправки нагадування: {e}")
    
    # Перетворюємо час у київський часовий пояс
    kyiv_tz = pytz.timezone('Europe/Kiev')
    if when.tzinfo is None:
        when = kyiv_tz.localize(when)
    
    scheduler.add_job(job, trigger=DateTrigger(run_date=when))
    logger.info(f"Заплановано нагадування на {when} для користувача {user_id}")

# ---------- Клавіатури ----------
main_keyboard = ReplyKeyboardMarkup([
    ["🏠 Головна", "👤 Профіль"],
    ["🍎 Калорії", "📅 План"],
    ["💪 Вправи", "⏰ Нагадування"],
    ["📈 Прогрес"]
], resize_keyboard=True)

profile_keyboard = ReplyKeyboardMarkup([
    ["🆕 Створити/Редагувати профіль"],
    ["👀 Перегляд профілю"],
    ["🎯 Змінити мету"],
    ["🔙 Назад"]
], resize_keyboard=True)

# Кнопки вибору цілей — використовуємо окрему клавіатуру (спадне меню)
goal_keyboard = ReplyKeyboardMarkup([
    ["Набір маси", "Схуднення", "Підтримання"],
    ["🔙 Назад"]
], resize_keyboard=True)

# Список груп м'язів — будуть показані при натисканні "Вправи"
muscle_groups = ["Спина", "Ноги", "Груди", "Плечі", "Біцепс", "Трицепс", "Передпліччя", "Сідниці"]
def muscle_groups_keyboard():
    rows = [[g] for g in muscle_groups]
    rows.append(["🔙 Назад"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def back_to_exercises_kb():
    kb = [[ "🔙 Назад до списку"], ["🔙 Назад"]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# Клавіатура для збереження файлів
save_keyboard = ReplyKeyboardMarkup([
    ["✅ Зберегти", "❌ Не зберігати"],
    ["🔙 Назад"]
], resize_keyboard=True)

# Нова клавіатура для меню прогресу
progress_keyboard = ReplyKeyboardMarkup([
    ["⚖️ Вага", "📏 Заміри"],
    ["💪 Тренування", "📊 Статистика"],
    ["🔙 Назад"]
], resize_keyboard=True)

# Клавіатура для введення прогресу (нова)
progress_input_keyboard = ReplyKeyboardMarkup([
    ["🔙 До вибору прогресу"]
], resize_keyboard=True)

# ---------- Conversation PROFILE ----------
(ASK_NAME, ASK_AGE, ASK_SEX, ASK_HEIGHT, ASK_WEIGHT, ASK_GOAL) = range(6)

# Додаємо новий стан для зміни цілі
CHANGE_GOAL = 6

# Стани для прогресу
WEIGHT_INPUT, MEASUREMENTS_INPUT, WORKOUT_INPUT = range(7, 10)
# Додаємо нові стани для покрокового введення тренування
WORKOUT_EXERCISE, WORKOUT_SETS, WORKOUT_REPS, WORKOUT_WEIGHT, WORKOUT_CONTINUE = range(10, 15)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🏋️ *Привіт! Я твій фітнес-бот!*\n\n"
        "Обирай дію з меню нижче або використовуй команди:\n\n"
        "🤖 *Доступні команди:*\n"
        "/start - Показати головне меню\n"
        "/callback - Зв'язок з розробником\n"
        "/create - Створити/редагувати профіль\n"
        "/calories - Калькулятор калорій\n"
        "/plan - План тренувань\n"
        "/statistics - Статистика прогресу\n\n"
        "Використовуй кнопки меню для зручної навігації! 👇"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=main_keyboard)

async def callback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для зв'язку з розробником"""
    try:
        # Намагаємося відправити картинку з текстом
        with open("helpa.jpg", "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption="Є питання щодо бота? Зв'яжіться з нами 👉 @amiyakatabaka 👨‍💻",
                reply_markup=main_keyboard
            )
    except FileNotFoundError:
        # Якщо файл не знайдено, відправляємо тільки текст
        await update.message.reply_text(
            "Є питання щодо бота? Зв'яжіться з нами 👉 @amiyakatabaka 👨‍💻",
            reply_markup=main_keyboard
        )
    except Exception as e:
        # Якщо сталася інша помилка, відправляємо тільки текст
        logger.error(f"Помилка при відправці фото: {e}")
        await update.message.reply_text(
            "Є питання щодо бота? Зв'яжіться з нами 👉 @amiyakatabaka 👨‍💻",
            reply_markup=main_keyboard
        )

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для створення/редагування профілю"""
    return await profile_start(update, context)

async def calories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для розрахунку калорій"""
    return await calories(update, context)

async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для показу плану тренувань"""
    return await plan(update, context)

async def statistics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для показу статистики"""
    return await show_statistics(update, context)

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка невідомих команд"""
    await update.message.reply_text(
        "❓ Невідома команда!\n\n"
        "🤖 *Доступні команди:*\n"
        "/start - Показати головне меню\n"
        "/callback - Зв'язок з розробником\n"
        "/create - Створити/редагувати профіль\n"
        "/calories - Калькулятор калорій\n"
        "/plan - План тренувань\n"
        "/statistics - Статистика прогресу\n\n"
        "Або використовуйте кнопки меню! 👇",
        parse_mode="Markdown",
        reply_markup=main_keyboard
    )

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👤 Меню профілю:", reply_markup=profile_keyboard)

async def profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Як вас звати?", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return ASK_NAME

async def profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    context.user_data['name'] = txt
    await update.message.reply_text("Вік?", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return ASK_AGE

async def profile_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    try:
        context.user_data['age'] = int(update.message.text.strip())
    except:
        await update.message.reply_text("Введіть число (вік).")
        return ASK_AGE
    await update.message.reply_text("Стать (Ч/Ж)?", reply_markup=ReplyKeyboardMarkup([["Ч","Ж"],["🔙 Назад"]], resize_keyboard=True))
    return ASK_SEX

async def profile_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    context.user_data['sex'] = update.message.text.strip().upper()
    await update.message.reply_text("Зріст (см)?", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return ASK_HEIGHT

async def profile_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    try:
        context.user_data['height'] = float(update.message.text.strip())
    except:
        await update.message.reply_text("Введіть число (зріст в см).")
        return ASK_HEIGHT
    await update.message.reply_text("Вага (кг)?", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return ASK_WEIGHT

async def profile_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    try:
        context.user_data['weight'] = float(update.message.text.strip())
    except:
        await update.message.reply_text("Введіть число (вага в кг).")
        return ASK_WEIGHT

    # Тепер запитуємо мету — через кнопки
    await update.message.reply_text("Оберіть мету:", reply_markup=goal_keyboard)
    return ASK_GOAL

async def profile_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END
    if text not in ["Набір маси", "Схуднення", "Підтримання"]:
        await update.message.reply_text("Оберіть одну з кнопок: Набір маси / Схуднення / Підтримання")
        return ASK_GOAL
    context.user_data['goal'] = text

    # Зберігаємо профіль
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''INSERT OR REPLACE INTO users 
        (user_id, username, name, age, sex, height_cm, weight_kg, goal, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
        (update.effective_user.id, update.effective_user.username,
         context.user_data['name'], context.user_data['age'], context.user_data['sex'],
         context.user_data['height'], context.user_data['weight'], context.user_data['goal'])
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Профіль збережено!", reply_markup=profile_keyboard)
    return ConversationHandler.END

async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
    return ConversationHandler.END

async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name, age, sex, height_cm, weight_kg, goal FROM users WHERE user_id=?", (update.effective_user.id,))
    user = cur.fetchone()
    conn.close()
    if user:
        name, age, sex, h, w, goal = user
        text = (f"👤 Профіль:\nІм'я: {name}\nВік: {age}\nСтать: {sex}\nЗріст: {h} см\nВага: {w} кг\nМета: {goal}")
    else:
        text = "❌ Профіль не знайдено. Створіть його."
    await update.message.reply_text(text, reply_markup=profile_keyboard)

async def change_goal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Починає процес зміни мети"""
    # Перевіряємо, чи існує профіль
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT goal FROM users WHERE user_id=?", (update.effective_user.id,))
    user = cur.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text("❌ Спочатку створіть профіль.", reply_markup=profile_keyboard)
        return ConversationHandler.END
    
    current_goal = user[0]
    await update.message.reply_text(
        f"🎯 Поточна мета: {current_goal}\n\nОберіть нову мету:",
        reply_markup=goal_keyboard
    )
    return CHANGE_GOAL

async def change_goal_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зберігає нову мету"""
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню профілю.", reply_markup=profile_keyboard)
        return ConversationHandler.END
    
    if text not in ["Набір маси", "Схуднення", "Підтримання"]:
        await update.message.reply_text("Оберіть одну з кнопок: Набір маси / Схуднення / Підтримання")
        return CHANGE_GOAL
    
    # Оновлюємо мету в базі даних
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET goal=? WHERE user_id=?", (text, update.effective_user.id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Мета змінена на: {text}", reply_markup=profile_keyboard)
    return ConversationHandler.END

async def cancel_change_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасування зміни мети"""
    await update.message.reply_text("Скасування. Повернення в меню профілю.", reply_markup=profile_keyboard)
    return ConversationHandler.END

# ---------- КАЛОРІЇ ----------
def save_to_file(user_id: int, content: str, prefix: str) -> str:
    """Зберігає контент у файл і повертає шлях до файлу"""
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join("user_files", str(user_id), filename)
    
    # Створюємо директорію якщо її немає
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filepath

async def calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sex, height_cm, weight_kg, age, goal FROM users WHERE user_id=?", (update.effective_user.id,))
    user = cur.fetchone()
    conn.close()

    if not user:
        await update.message.reply_text("❌ Спочатку створіть профіль.", reply_markup=main_keyboard)
        return

    sex, h, w, age, goal = user

    # --- Розрахунок калорій ---
    # Формула Міффліна-Сан Жеора
    bmr = 10 * w + 6.25 * h - 5 * age + (5 if sex.upper() == "Ч" else -161)
    tdee = bmr * 1.55  # коефіцієнт активності (помірна активність)

    # Корекція під мету
    if goal == "Схуднення":
        tdee_adj = tdee * 0.85
    elif goal == "Набір маси":
        tdee_adj = tdee * 1.15
    else:
        tdee_adj = tdee

    # --- Формуємо пояснення ---
    text = (
        f"🍎 *Розрахунок калорій для вас*\n\n"
        f"📏 Зріст: {h} см\n⚖️ Вага: {w} кг\n🎂 Вік: {age}\nСтать: {sex}\nМета: {goal}\n\n"
        f"💡 Використовується формула *Міффліна — Сан Жеора*:\n"
        f"`BMR = 10 × вага + 6.25 × зріст - 5 × вік + (5 для чоловіків / -161 для жінок)`\n\n"
        f"➡️ Ваш базовий обмін (BMR): *{int(bmr)} ккал/день*\n"
        f"➡️ Враховуючи активність (×1.55): *{int(tdee)} ккал/день*\n"
        f"➡️ З поправкою на мету ({goal}): *{int(tdee_adj)} ккал/день*\n\n"
        f"🔥 *Підсумкова норма: {int(tdee_adj)} ккал/день*\n"
    )

    # --- План харчування ---
    kcal = int(tdee_adj)
    protein = int((0.3 * kcal) / 4)
    fat = int((0.25 * kcal) / 9)
    carbs = int((0.45 * kcal) / 4)

    text += (
        f"\n🥗 *Рекомендований план харчування:*\n"
        f"Білки: ~{protein} г ({int(protein*4)} ккал)\n"
        f"Жири: ~{fat} г ({int(fat*9)} ккал)\n"
        f"Вуглеводи: ~{carbs} г ({int(carbs*4)} ккал)\n\n"
    )

    # Приблизний розподіл по прийомах їжі
    text += (
        f"🍳 *Приблизне меню на день:*\n"
        f"• Сніданок — 25% ({int(kcal*0.25)} ккал): вівсянка, яйця, фрукти\n"
        f"• Обід — 35% ({int(kcal*0.35)} ккал): рис/гречка, курка/риба, овочі\n"
        f"• Перекус — 15% ({int(kcal*0.15)} ккал): сир, горіхи, фрукти\n"
        f"• Вечеря — 25% ({int(kcal*0.25)} ккал): овочі, білок (м'ясо/риба), трохи крупи\n\n"
        f"💧 Не забувайте пити воду — не менше 30 мл на 1 кг ваги!"
    )

    # Зберігаємо текст розрахунку калорій в контекст
    context.user_data['calories_text'] = text
    
    # Спочатку показуємо результат розрахунку
    await update.message.reply_text(text, parse_mode="Markdown")
    # Потім запитуємо про збереження
    await update.message.reply_text(
        "Хочете зберегти розрахунок калорій у файл?",
        reply_markup=save_keyboard
    )

async def handle_calories_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text
    
    if response == "✅ Зберегти":
        if 'calories_text' in context.user_data:
            try:
                filepath = save_to_file(
                    update.effective_user.id,
                    context.user_data['calories_text'],
                    'calories'
                )
                with open(filepath, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption="📊 Ваш розрахунок калорій"
                    )
            except Exception as e:
                await update.message.reply_text(
                    "❌ Помилка при збереженні файлу",
                    reply_markup=main_keyboard
                )
        else:
            await update.message.reply_text(
                "❌ Дані для збереження не знайдено",
                reply_markup=main_keyboard
            )
    
    # Очищуємо дані калорій після обробки
    context.user_data.pop('calories_text', None)
    
    # В будь-якому випадку (зберегти чи ні) — повертаємо в головне меню
    await update.message.reply_text(
        "Повернення в головне меню",
        reply_markup=main_keyboard
    )

# ---------- ПЛАН ----------
async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sex, height_cm, weight_kg, age, goal FROM users WHERE user_id=?", (update.effective_user.id,))
    user = cur.fetchone()
    conn.close()

    if not user:
        await update.message.reply_text("❌ Спочатку створіть профіль.", reply_markup=main_keyboard)
        return

    sex, h, w, age, goal = user

    # Визначаємо рівень користувача по віку
    if age < 25:
        level = "початковий"
    elif age < 40:
        level = "середній"
    else:
        level = "помірний"

    # Плани тренувань з урахуванням віку та мети
    plans = {
        "Схуднення": {
            "початковий": {
                "title": "🔥 План схуднення для початківців (до 25 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування на тиждень\n— 20-30 хв кардіо\n— Базові вправи з вагою тіла\n— Акцент на техніку виконання\n",
                    "Тиждень 2️⃣:\n— 3-4 тренування\n— Легкі інтервальні тренування\n— Збільшення часу кардіо до 30 хв\n",
                    "Тиждень 3️⃣:\n— 4 тренування\n— Кругові тренування по 15-20 хв\n— Додавання легких гантелей\n",
                    "Тиждень 4️⃣:\n— 4-5 тренувань\n— HIIT 15-20 хв\n— Комбіновані тренування"
                ]
            },
            "середній": {
                "title": "🔥 План схуднення для середнього рівня (25-40 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 4 тренування\n— 30-40 хв кардіо\n— Силові + кардіо\n— Контроль харчування\n",
                    "Тиждень 2️⃣:\n— 4-5 тренувань\n— HIIT 20-25 хв\n— Збільшення навантаження в силових\n",
                    "Тиждень 3️⃣:\n— 5 тренувань\n— Складні кругові тренування\n— Кардіо натще\n",
                    "Тиждень 4️⃣:\n— 5-6 тренувань\n— Комбіновані HIIT\n— Силові суперсети"
                ]
            },
            "помірний": {
                "title": "🔥 План схуднення для старшого віку (40+)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування\n— Низькоінтенсивне кардіо 20-30 хв\n— Вправи на гнучкість\n",
                    "Тиждень 2️⃣:\n— 3-4 тренування\n— Помірне кардіо\n— Силові з власною вагою\n",
                    "Тиждень 3️⃣:\n— 4 тренування\n— Плавання або велосипед\n— Силові з легкою вагою\n",
                    "Тиждень 4️⃣:\n— 4 тренування\n— Комбіновані тренування\n— Стретчинг"
                ]
            }
        },
        "Набір маси": {
            "початковий": {
                "title": "💪 План набору маси для початківців (до 25 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування\n— Базові вправи\n— 3х8-10 повторень\n— Фокус на техніку\n",
                    "Тиждень 2️⃣:\n— 4 тренування\n— Збільшення ваг\n— Базові вправи + ізольовані\n",
                    "Тиждень 3️⃣:\n— 4 тренування\n— Спліт-програма\n— Збільшення об'єму\n",
                    "Тиждень 4️⃣:\n— 5 тренувань\n— Повноцінний спліт\n— Прогресивне перевантаження"
                ]
            },
            "середній": {
                "title": "💪 План набору маси для середнього рівня (25-40 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 4 тренування\n— Складні базові рухи\n— 4х8-12 повторень\n",
                    "Тиждень 2️⃣:\n— 4-5 тренувань\n— Збільшення робочих ваг\n— Додавання дроп-сетів\n",
                    "Тиждень 3️⃣:\n— 5 тренувань\n— Пірамідальні підходи\n— Суперсети\n",
                    "Тиждень 4️⃣:\n— 5 тренувань\n— Максимальні ваги\n— Робота до відмови"
                ]
            },
            "помірний": {
                "title": "💪 План набору маси для старшого віку (40+)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування\n— Помірні ваги\n— 3х10-15 повторень\n— Акцент на відновлення\n",
                    "Тиждень 2️⃣:\n— 3-4 тренування\n— Поступове збільшення навантаження\n— Контроль техніки\n",
                    "Тиждень 3️⃣:\n— 4 тренування\n— Середні ваги\n— Якісні повторення\n",
                    "Тиждень 4️⃣:\n— 4 тренування\n— Оптимальні ваги\n— Контроль відновлення"
                ]
            }
        },
        "Підтримання": {
            "початковий": {
                "title": "⚖️ План підтримання форми для початківців (до 25 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування\n— Комбіновані тренування\n— 20 хв кардіо\n",
                    "Тиждень 2️⃣:\n— 3-4 тренування\n— Різноманітні вправи\n— Кардіо + силова\n",
                    "Тиждень 3️⃣:\n— 4 тренування\n— Збільшення інтенсивності\n— Функціональний тренінг\n",
                    "Тиждень 4️⃣:\n— 4 тренування\n— Змішані тренування\n— Активний відпочинок"
                ]
            },
            "середній": {
                "title": "⚖️ План підтримання форми для середнього рівня (25-40 років)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 4 тренування\n— Силовий + функціональний тренінг\n— Йога або стретчинг\n",
                    "Тиждень 2️⃣:\n— 4 тренування\n— Елементи кросфіту\n— Кардіо дні\n",
                    "Тиждень 3️⃣:\n— 4-5 тренувань\n— Інтервальні тренування\n— Силові дні\n",
                    "Тиждень 4️⃣:\n— 4-5 тренувань\n— Змішані навантаження\n— Активне відновлення"
                ]
            },
            "помірний": {
                "title": "⚖️ План підтримання форми для старшого віку (40+)",
                "weeks": [
                    "Тиждень 1️⃣:\n— 3 тренування\n— Легкі кардіо\n— Вправи на рівновагу\n",
                    "Тиждень 2️⃣:\n— 3-4 тренування\n— Йога і стретчинг\n— Силові з малою вагою\n",
                    "Тиждень 3️⃣:\n— 3-4 тренування\n— Плавання\n— Суглобова гімнастика\n",
                    "Тиждень 4️⃣:\n— 3-4 тренування\n— Пілатес\n— Відновлювальні практики"
                ]
            }
        }
    }

    # Вибираємо план на основі цілі та рівня
    selected_plan = plans[goal][level]
    text = f"{selected_plan['title']}\n\n"
    
    # Додаємо тижні плану
    for week in selected_plan['weeks']:
        text += f"{week}\n"

    # Додаємо рекомендації по віковій групі
    age_recommendations = {
        "початковий": "\n🎯 Рекомендації:\n- Фокусуйтеся на правильній техніці\n- Поступово збільшуйте навантаження\n- Достатній сон (8-9 годин)\n- Правильне харчування",
        "середній": "\n🎯 Рекомендації:\n- Слідкуйте за відновленням\n- Розминка перед кожним тренуванням\n- Збалансоване харчування\n- 7-8 годин сну",
        "помірний": "\n🎯 Рекомендації:\n- Обов'язкова розминка і заминка\n- Контроль навантаження\n- Регулярний відпочинок\n- Консультація з лікарем за необхідності"
    }
    
    text += f"\n{age_recommendations[level]}"
    
    # Зберігаємо текст плану тренувань в контекст
    context.user_data['training_plan'] = text
    
    # Спочатку показуємо план
    await update.message.reply_text(text, parse_mode="Markdown")
    # Потім запитуємо про збереження
    await update.message.reply_text(
        "Хочете зберегти план тренувань у файл?",
        reply_markup=save_keyboard
    )

async def handle_plan_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text
    
    if response == "✅ Зберегти":
        if 'training_plan' in context.user_data:
            try:
                filepath = save_to_file(
                    update.effective_user.id,
                    context.user_data['training_plan'],
                    'training_plan'
                )
                with open(filepath, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=os.path.basename(filepath),
                        caption="📋 Ваш план тренувань"
                    )
            except Exception as e:
                await update.message.reply_text(
                    "❌ Помилка при збереженні файлу",
                    reply_markup=main_keyboard
                )
        else:
            await update.message.reply_text(
                "❌ Дані для збереження не знайдено",
                reply_markup=main_keyboard
            )
    
    # Очищаємо дані плану після обробки
    context.user_data.pop('training_plan', None)
    
    # В будь-якому випадку (зберегти чи ні) — повертаємо в головне меню
    await update.message.reply_text(
        "Повернення в головне меню",
        reply_markup=main_keyboard
    )

# ---------- ВПРАВИ: меню груп -> вправи -> деталі ----------
async def exercises_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати список груп м'язів"""
    await update.message.reply_text("Оберіть групу м'язів:", reply_markup=muscle_groups_keyboard())
    context.user_data['in_exercises'] = True
    # очистимо тимчасові ключі
    context.user_data.pop('selected_group', None)

async def exercises_group_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Повернення в головне меню", reply_markup=main_keyboard)
        context.user_data['in_exercises'] = False
        return

    # Якщо обрали групу м'язів — покажемо вправи цієї групи
    if text in muscle_groups:
        group = text
        context.user_data['selected_group'] = group
        context.user_data['in_exercises'] = True  # Встановлюємо прапор

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM exercises WHERE muscle_group=? ORDER BY name", (group,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("Поки що немає вправ у цій групі.", reply_markup=muscle_groups_keyboard())
            return

        buttons = [[r[0]] for r in rows]
        buttons.append(["🔙 Назад"])
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        await update.message.reply_text(f"Вправи — {group}:", reply_markup=keyboard)
        return
    # якщо не група — просто ігноруємо тут (повинен зловити інший handler)
    await update.message.reply_text("Оберіть групу м'язів зі списку.", reply_markup=muscle_groups_keyboard())

async def back_to_exercise_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повернення до списку вправ обраної групи"""
    selected_group = context.user_data.get('selected_group')
    if selected_group:
        # Показуємо вправи вибраної групи
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM exercises WHERE muscle_group=? ORDER BY name", (selected_group,))
        rows = cur.fetchall()
        conn.close()

        if rows:
            buttons = [[r[0]] for r in rows]
            buttons.append(["🔙 Назад"])  # Кнопка для повернення до груп м'язів
            keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
            await update.message.reply_text(f"Вправи — {selected_group}:", reply_markup=keyboard)
        else:
            await update.message.reply_text("Поки що немає вправ у цій групі.", reply_markup=muscle_groups_keyboard())
    else:
        # Якщо немає обраної групи, повертаємося до вибору груп
        await update.message.reply_text("Оберіть групу м'язів:", reply_markup=muscle_groups_keyboard())

async def exercise_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    
    if name == "🔙 Назад":
        # Якщо є обрана група, повертаємося до списку груп м'язів
        if context.user_data.get('selected_group'):
            await update.message.reply_text("Оберіть групу м'язів:", reply_markup=muscle_groups_keyboard())
            context.user_data.pop('selected_group', None)
        else:
            # Інакше повертаємося в головне меню
            await update.message.reply_text("Повернення в головне меню", reply_markup=main_keyboard)
            context.user_data['in_exercises'] = False
        return

    # Показати детальну інформацію про вправу
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Намагаємося точний збіг
    cur.execute("SELECT muscle_group, muscles, description, demo_url FROM exercises WHERE name=?", (name,))
    row = cur.fetchone()
    
    # Якщо не знайдено точний збіг, намагаємося пошук по частковому збігу
    if not row:
        cur.execute("SELECT name, muscle_group, muscles, description, demo_url FROM exercises WHERE name LIKE ?", (f"%{name}%",))
        rows = cur.fetchall()
        if rows:
            if len(rows) == 1:
                # Знайдено одну вправу
                name, group, muscles, desc, url = rows[0]
                row = (group, muscles, desc, url)
            else:
                # Знайдено кілька вправ, покажемо список
                conn.close()
                suggestions = "\n".join([f"• {r[0]}" for r in rows[:5]])  # показуємо перші 5
                await update.message.reply_text(
                    f"❓ Знайдено кілька вправ:\n\n{suggestions}\n\nОберіть точну назву.",
                    reply_markup=main_keyboard
                )
                return
    
    conn.close()

    if not row:
        # Не знайдено — можливо натиснули щось інше
        await update.message.reply_text("❌ Вправу не знайдено. Оберіть з меню.", reply_markup=main_keyboard)
        return

    group, muscles, desc, url = row
    
    # Безпечне формування тексту без Markdown
    try:
        text = (f"🏋️ {name}\n\n"
                f"Група: {group}\n"
                f"М'язи: {muscles}\n\n"
                f"Як виконувати:\n{desc}\n\n"
                f"🎥 Демонстрація: {url}")
        
        await update.message.reply_text(
            text, 
            reply_markup=ReplyKeyboardMarkup([["🔙 Назад до списку"], ["🔙 Назад"]], resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"Error sending exercise details: {e}")
        # Відправляємо спрощене повідомлення у випадку помилки
        await update.message.reply_text(
            f"🏋️ {name}\n\nІнформація про вправу тимчасово недоступна.",
            reply_markup=ReplyKeyboardMarkup([["🔙 Назад до списку"], ["🔙 Назад"]], resize_keyboard=True)
        )

# ---------- Нагадування ----------

# Етапи діалогу
(ASK_REMIND_DATE, ASK_REMIND_TIME, ASK_REMIND_TEXT) = range(3)

async def remind_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запускає процес встановлення нагадування"""
    await update.message.reply_text(
        "📅 Введи дату нагадування у форматі *ДД.ММ.РРРР* (наприклад 13.10.2025):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    )
    return ASK_REMIND_DATE


async def remind_ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує дату і просить час"""
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END

    try:
        remind_date = datetime.strptime(text, "%d.%m.%Y").date()
        context.user_data["remind_date"] = remind_date
        await update.message.reply_text(
            "⏰ Тепер введи час у форматі *ГГ:ХХ* (наприклад 07:30):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
        )
        return ASK_REMIND_TIME
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Спробуй знову (приклад: 13.10.2025).")
        return ASK_REMIND_DATE


async def remind_ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує час і просить текст нагадування"""
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END

    try:
        # допустимий формат ГГ:ХХ
        if ":" not in text:
            raise ValueError("немає двокрапки")
        hour_min = text.split(":")
        if len(hour_min) != 2:
            raise ValueError("поганий розділ")

        hour, minute = map(int, hour_min)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("поза діапазоном")

        date_part = context.user_data.get("remind_date")
        if not date_part:
            await update.message.reply_text("❌ Не знайдено дату. Почни заново через кнопку ⏰ Нагадування.")
            return ConversationHandler.END

        when = datetime.combine(date_part, datetime.min.time()).replace(hour=hour, minute=minute)
        
        # Перевіряємо час у київському часовому поясі
        kyiv_tz = pytz.timezone('Europe/Kiev')
        now = datetime.now(kyiv_tz).replace(tzinfo=None)
        
        if when <= now:
            await update.message.reply_text("❌ Цей час уже минув. Вкажи майбутній час.")
            return ASK_REMIND_TIME

        # Зберігаємо час і переходимо до введення тексту
        context.user_data["remind_datetime"] = when
        await update.message.reply_text(
            "✍️ Введи текст нагадування (наприклад: 'Тренування у залі'):",
            reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
        )
        return ASK_REMIND_TEXT

    except ValueError:
        await update.message.reply_text("❌ Невірний формат часу. Приклад: 07:30")
        return ASK_REMIND_TIME

async def remind_ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує текст нагадування і встановлює його"""
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        return ConversationHandler.END

    remind_datetime = context.user_data.get("remind_datetime")
    if not remind_datetime:
        await update.message.reply_text("❌ Помилка — не знайдено дату/час. Спробуйте знову.", reply_markup=main_keyboard)
        return ConversationHandler.END

    remind_text = text
    
    # Плануємо нагадування
    schedule_reminder(update.effective_user.id, remind_datetime, remind_text)
    
    await update.message.reply_text(
        f"✅ Нагадування встановлено на {remind_datetime.strftime('%d.%m.%Y %H:%M')} (київський час)!\nТекст: {remind_text}",
        reply_markup=main_keyboard
    )
    
    # очистимо тимчасові дані
    context.user_data.pop("remind_date", None)
    context.user_data.pop("remind_datetime", None)
    return ConversationHandler.END

async def remind_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Якщо користувач ввів текст нагадування після часу — зберігаємо і плануємо"""
    text = update.message.text.strip()
    if text == "🔙 Назад":
        await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
        context.user_data.pop("awaiting_remind_text", None)
        context.user_data.pop("remind_date", None)
        context.user_data.pop("remind_datetime", None)
        return ConversationHandler.END

    if not context.user_data.get("awaiting_remind_text"):
        await update.message.reply_text("Я не зрозумів. Будь ласка, натисніть кнопку меню.", reply_markup=main_keyboard)
        return ConversationHandler.END

    remind_datetime = context.user_data.get("remind_datetime")
    if not remind_datetime:
        await update.message.reply_text("❌ Помилка — не знайдено дату/час. Спробуйте знову.", reply_markup=main_keyboard)
        context.user_data.pop("awaiting_remind_text", None)
        return ConversationHandler.END

    remind_text = text
    schedule_reminder(context.application, update.effective_user.id, remind_datetime, remind_text)

    await update.message.reply_text(
        f"✅ Нагадування встановлено на {remind_datetime.strftime('%d.%m.%Y %H:%M')}!\nТекст: {remind_text}",
        reply_markup=main_keyboard
    )
    # очистимо тимчасові дані
    context.user_data.pop("awaiting_remind_text", None)
    context.user_data.pop("remind_date", None)
    context.user_data.pop("remind_datetime", None)
    return ConversationHandler.END

async def cancel_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скасування встановлення нагадування"""
    await update.message.reply_text("Скасування. Повернення в меню.", reply_markup=main_keyboard)
    # очищення контексту
    context.user_data.pop("awaiting_remind_text", None)
    context.user_data.pop("remind_date", None)
    context.user_data.pop("remind_datetime", None)
    return ConversationHandler.END

# ---------- ПРОГРЕС ----------
async def progress_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати меню прогресу"""
    await update.message.reply_text("📈 Оберіть тип прогресу:", reply_markup=progress_keyboard)

async def track_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відстеження ваги"""
    context.user_data['progress_state'] = 'weight'
    await update.message.reply_text(
        "⚖️ Відстеження ваги\n\nВведіть вашу поточну вагу в кг (наприклад: 75.5):",
        reply_markup=progress_input_keyboard
    )
    return WEIGHT_INPUT

async def handle_weight_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка введення ваги"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        await progress_menu(update, context)
        return ConversationHandler.END
    
    try:
        weight = float(text.replace(',', '.'))  # Підтримуємо як крапку, так і кому
        
        if weight <= 0 or weight > 500:  # Розумні межі ваги
            raise ValueError("Weight out of range")
            
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO weight_progress 
            (user_id, date, weight)
            VALUES (?, date('now'), ?)""",
            (update.effective_user.id, weight)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Вага {weight} кг успішно записана!",
            reply_markup=progress_keyboard
        )
        await progress_menu(update, context)
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Невірний формат. Введіть вагу в кг (наприклад: 75.5)",
            reply_markup=progress_input_keyboard
        )
        return WEIGHT_INPUT

async def track_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відстеження замірів"""
    context.user_data['progress_state'] = 'measurements'
    await update.message.reply_text(
        "📏 Відстеження замірів\n\nВведіть заміри у форматі:\nгруди талія стегна біцепс стегно\n\nПриклад: 100 80 95 35 55",
        reply_markup=progress_input_keyboard
    )
    return MEASUREMENTS_INPUT

async def track_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відстеження тренувань - покрокове введення"""
    context.user_data['workout_data'] = []  # Список для зберігання вправ
    await update.message.reply_text(
        "💪 Відстеження тренувань\n\nВведіть назву вправи:",
        reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
    )
    return WORKOUT_EXERCISE

async def handle_workout_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує назву вправи"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        context.user_data.pop('workout_data', None)
        await progress_menu(update, context)
        return ConversationHandler.END
    
    context.user_data['current_exercise'] = text
    await update.message.reply_text(
        f"Вправа: {text}\n\nВведіть кількість підходів:",
        reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
    )
    return WORKOUT_SETS

async def handle_workout_sets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує кількість підходів"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        context.user_data.pop('workout_data', None)
        context.user_data.pop('current_exercise', None)
        await progress_menu(update, context)
        return ConversationHandler.END
    
    try:
        sets = int(text)
        if sets <= 0 or sets > 20:
            raise ValueError("Invalid sets range")
        
        context.user_data['current_sets'] = sets
        await update.message.reply_text(
            f"Підходи: {sets}\n\nВведіть кількість повторень:",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_REPS
        
    except ValueError:
        await update.message.reply_text(
            "❌ Введіть число від 1 до 20",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_SETS

async def handle_workout_reps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує кількість повторень"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        context.user_data.pop('workout_data', None)
        context.user_data.pop('current_exercise', None)
        context.user_data.pop('current_sets', None)
        await progress_menu(update, context)
        return ConversationHandler.END
    
    try:
        reps = int(text)
        if reps <= 0 or reps > 100:
            raise ValueError("Invalid reps range")
        
        context.user_data['current_reps'] = reps
        await update.message.reply_text(
            f"Повторення: {reps}\n\nВведіть вагу (в кг, якщо без ваги - введіть 0):",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_WEIGHT
        
    except ValueError:
        await update.message.reply_text(
            "❌ Введіть число від 1 до 100",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_REPS

async def handle_workout_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує вагу і запитує про продовження"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        context.user_data.pop('workout_data', None)
        context.user_data.pop('current_exercise', None)
        context.user_data.pop('current_sets', None)
        context.user_data.pop('current_reps', None)
        await progress_menu(update, context)
        return ConversationHandler.END
    
    try:
        weight = float(text)
        if weight < 0 or weight > 500:
            raise ValueError("Invalid weight range")
        
        # Зберігаємо поточну вправу
        exercise_data = {
            'exercise': context.user_data['current_exercise'],
            'sets': context.user_data['current_sets'],
            'reps': context.user_data['current_reps'],
            'weight': weight
        }
        
        if 'workout_data' not in context.user_data:
            context.user_data['workout_data'] = []
        context.user_data['workout_data'].append(exercise_data)
        
        # Показуємо що записали і запитуємо про продовження
        exercise_text = f"✅ Записано: {exercise_data['exercise']} - {exercise_data['sets']}×{exercise_data['reps']} з вагою {exercise_data['weight']}кг"
        
        await update.message.reply_text(
            f"{exercise_text}\n\nХочете додати ще одну вправу?",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Додати ще", "💾 Завершити тренування"],
                ["🔙 До вибору прогресу"]
            ], resize_keyboard=True)
        )
        return WORKOUT_CONTINUE
        
    except ValueError:
        await update.message.reply_text(
            "❌ Введіть число від 0 до 500",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_WEIGHT

async def handle_workout_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє вибір продовження або завершення тренування"""
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        context.user_data.pop('workout_data', None)
        await progress_menu(update, context)
        return ConversationHandler.END
    
    elif text == "✅ Додати ще":
        # Очищаємо дані поточної вправи і починаємо нову
        context.user_data.pop('current_exercise', None)
        context.user_data.pop('current_sets', None)
        context.user_data.pop('current_reps', None)
        
        await update.message.reply_text(
            "💪 Введіть назву наступної вправи:",
            reply_markup=ReplyKeyboardMarkup([["🔙 До вибору прогресу"]], resize_keyboard=True)
        )
        return WORKOUT_EXERCISE
    
    elif text == "💾 Завершити тренування":
        # Зберігаємо все тренування в БД
        workout_data = context.user_data.get('workout_data', [])
        
        if not workout_data:
            await update.message.reply_text(
                "❌ Немає даних для збереження",
                reply_markup=progress_keyboard
            )
            await progress_menu(update, context)
            return ConversationHandler.END
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        for exercise in workout_data:
            cur.execute(
                """INSERT INTO workout_progress 
                (user_id, date, exercise, sets, reps, weight)
                VALUES (?, date('now'), ?, ?, ?, ?)""",
                (update.effective_user.id, exercise['exercise'], 
                 exercise['sets'], exercise['reps'], exercise['weight'])
            )
        
        # Отримуємо статистику по тренуванням
        cur.execute("""
            SELECT 
                COUNT(DISTINCT date) as total_workouts,
                COUNT(*) as total_exercises,
                COUNT(DISTINCT exercise) as unique_exercises,
                MAX(date) as last_workout_date
            FROM workout_progress 
            WHERE user_id=?
        """, (update.effective_user.id,))
        
        stats = cur.fetchone()
        total_workouts, total_exercises, unique_exercises, last_date = stats
        
        # Отримуємо статистику за останні 7 днів
        cur.execute("""
            SELECT COUNT(DISTINCT date) 
            FROM workout_progress 
            WHERE user_id=? AND date >= date('now', '-7 days')
        """, (update.effective_user.id,))
        
        workouts_last_week = cur.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Формуємо підсумок тренування і загальну статистику
        summary = "✅ Тренування збережено!\n\n💪 *Виконані вправи:*\n"
        total_volume = 0  # Загальний тоннаж
        for i, exercise in enumerate(workout_data, 1):
            volume = exercise['sets'] * exercise['reps'] * exercise['weight']
            total_volume += volume
            weight_str = f"{exercise['weight']}кг" if exercise['weight'] > 0 else "без ваги"
            summary += f"{i}. {exercise['exercise']}: {exercise['sets']}×{exercise['reps']} ({weight_str})\n"
        
        summary += f"\n📊 *Загальний тоннаж:* {total_volume:.1f} кг\n\n"
        
        # Додаємо загальну статистику
        summary += f"📈 *Ваша статистика:*\n"
        summary += f"• Всього тренувань: {total_workouts}\n"
        summary += f"• Всього вправ: {total_exercises}\n"
        summary += f"• Унікальних вправ: {unique_exercises}\n"
        summary += f"• Тренувань за тиждень: {workouts_last_week}\n"
        
        # Очищаємо дані тренування
        context.user_data.pop('workout_data', None)
        context.user_data.pop('current_exercise', None)
        context.user_data.pop('current_sets', None)
        context.user_data.pop('current_reps', None)
        
        await update.message.reply_text(
            summary,
            parse_mode="Markdown",
            reply_markup=progress_keyboard
        )
        await progress_menu(update, context)
        return ConversationHandler.END
    
    else:
        await update.message.reply_text(
            "❌ Невідома команда",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Додати ще", "💾 Завершити тренування"],
                ["🔙 До вибору прогресу"]
            ], resize_keyboard=True)
        )
        return WORKOUT_CONTINUE

async def handle_measurements_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "🔙 До вибору прогресу":
        await progress_menu(update, context)
        return ConversationHandler.END
    
    try:
        measurements = list(map(float, text.split()))
        if len(measurements) != 5:
            raise ValueError("Wrong number of measurements")
            
        chest, waist, hips, biceps, thighs = measurements
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO measurement_progress 
            (user_id, date, chest, waist, hips, biceps, thighs)
            VALUES (?, date('now'), ?, ?, ?, ?, ?)""",
            (update.effective_user.id, chest, waist, hips, biceps, thighs)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "✅ Заміри успішно записані!",
            reply_markup=progress_keyboard
        )
        await progress_menu(update, context)
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Невірний формат. Введіть 5 чисел через пробіл\nПриклад: 100 80 95 35 55",
            reply_markup=progress_input_keyboard
        )
        return MEASUREMENTS_INPUT

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показати детальну статистику"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    text = "📊 *Ваша детальна статистика:*\n\n"
    
    # Статистика ваги
    cur.execute("SELECT date, weight FROM weight_progress WHERE user_id=? ORDER BY date DESC LIMIT 10", (update.effective_user.id,))
    weight_records = cur.fetchall()
    
    if weight_records:
        text += "⚖️ *Записи ваги (останні 10):*\n"
        for date, weight in weight_records:
            text += f"• {date}: {weight} кг\n"
        text += "\n"
    
    # Статистика замірів
    cur.execute("SELECT date, chest, waist, hips, biceps, thighs FROM measurement_progress WHERE user_id=? ORDER BY date DESC LIMIT 5", (update.effective_user.id,))
    measurement_records = cur.fetchall()
    
    if measurement_records:
        text += "📏 *Записи замірів (останні 5):*\n"
        for date, chest, waist, hips, biceps, thighs in measurement_records:
            text += f"• {date}:\n"
            text += f"  Груди: {chest}см, Талія: {waist}см\n"
            text += f"  Стегна: {hips}см, Біцепс: {biceps}см, Стегно: {thighs}см\n\n"
    
    # Статистика тренувань (групуємо по днях)
    cur.execute("""
        SELECT date, exercise, sets, reps, weight 
        FROM workout_progress 
        WHERE user_id=? 
        ORDER BY date DESC, id DESC 
        LIMIT 20
    """, (update.effective_user.id,))
    workout_records = cur.fetchall()
    
    if workout_records:
        text += "💪 *Записи тренувань (останні 20):*\n"
        current_date = None
        
        for date, exercise, sets, reps, weight in workout_records:
            if current_date != date:
                if current_date is not None:
                    text += "\n"
                text += f"📅 *{date}:*\n"
                current_date = date
            
            weight_str = f"{weight}кг" if weight > 0 else "без ваги"
            text += f"• {exercise}: {sets}×{reps} ({weight_str})\n"
        text += "\n"
    
    # Загальна статистика
    cur.execute("SELECT COUNT(*) FROM weight_progress WHERE user_id=?", (update.effective_user.id,))
    weight_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM workout_progress WHERE user_id=?", (update.effective_user.id,))
    workout_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM measurement_progress WHERE user_id=?", (update.effective_user.id,))
    measurement_count = cur.fetchone()[0]
    
    if weight_count == 0 and workout_count == 0 and measurement_count == 0:
        text = "📊 У вас поки немає даних для статистики.\n\nДодайте записи про вагу, тренування або заміри."
    else:
        text += f"📋 *Загальна статистика:*\n"
        text += f"⚖️ Всього записів ваги: {weight_count}\n"
        text += f"💪 Всього записів тренувань: {workout_count}\n"
        text += f"📏 Всього записів замірів: {measurement_count}\n"
    
    conn.close()
    
    # Розбиваємо довге повідомлення на частини якщо потрібно
    if len(text) > 4000:
        parts = []
        current_part = ""
        
        for line in text.split('\n'):
            if len(current_part + line + '\n') > 4000:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        
        if current_part:
            parts.append(current_part)
        
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, parse_mode="Markdown", reply_markup=progress_keyboard)
            else:
                await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=progress_keyboard)

# ---------- Router для кнопок меню ----------
async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🏠 Головна":
        await start(update, context)
    elif text == "👤 Профіль":
        await profile_menu(update, context)
    elif text == "🆕 Створити/Редагувати профіль":
        return await profile_start(update, context)
    elif text == "👀 Перегляд профілю":
        await view_profile(update, context)
    elif text == "🎯 Змінити мету":
        return await change_goal_start(update, context)
    elif text == "🍎 Калорії":
        # Очищуємо старі дані перед новим розрахунком
        context.user_data.pop('training_plan', None)
        await calories(update, context)
    elif text == "📅 План":
        # Очищуємо старі дані перед новим планом
        context.user_data.pop('calories_text', None)
        await plan(update, context)
    elif text == "💪 Вправи":
        await exercises_menu(update, context)
    elif text == "⏰ Нагадування":
        return await remind_start(update, context)
    elif text == "📈 Прогрес":
        await progress_menu(update, context)
    elif text == "⚖️ Вага":
        return await track_weight(update, context)
    elif text == "📏 Заміри":
        return await track_measurements(update, context)
    elif text == "📊 Статистика":
        await show_statistics(update, context)
    elif text == "🔙 Назад":
        await update.message.reply_text("Повернення в головне меню", reply_markup=main_keyboard)
    elif text == "🔙 До вибору прогресу":
        await progress_menu(update, context)
    elif text == "✅ Зберегти":
        # Визначаємо що зберігати за пріоритетом: план важливіший за калорії
        if 'training_plan' in context.user_data:
            await handle_plan_save(update, context)
        elif 'calories_text' in context.user_data:
            await handle_calories_save(update, context)
        else:
            await update.message.reply_text("Повернення в головне меню", reply_markup=main_keyboard)
    elif text == "❌ Не зберігати":
        # Очищаємо всі дані і повертаємо в меню
        context.user_data.pop('calories_text', None)
        context.user_data.pop('training_plan', None)
        await update.message.reply_text("Повернення в головне меню", reply_markup=main_keyboard)
    else:
        # якщо не розпізнали — інше обробить
        await update.message.reply_text("Не зрозумів команду. Оберіть кнопку з меню.", reply_markup=main_keyboard)

# ---------- Фоллбек ----------
async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я не зрозумів. Будь ласка, натисніть кнопку меню.", reply_markup=main_keyboard)

# ---------- MAIN ----------
def main():
    init_db()
    seed_exercises()

    app = Application.builder().token(BOT_TOKEN).build()
    
    # Встановлюємо глобальну змінну bot
    global bot_instance
    bot_instance = app.bot

    # Додаємо обробник помилок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Якщо є update і можна відправити повідомлення користувачу
        if update and hasattr(update, 'effective_message') and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Сталася помилка. Спробуйте ще раз або використовуйте головне меню.",
                    reply_markup=main_keyboard
                )
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")
    
    app.add_error_handler(error_handler)

    # Conversation для профілю - повинен бути ПЕРШИМ
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^🆕 Створити/Редагувати профіль$'), profile_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_name)],
            ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_age)],
            ASK_SEX: [MessageHandler(filters.Regex(r'^(Ч|Ж|ч|ж)$') | (filters.TEXT & ~filters.COMMAND), profile_sex)],
            ASK_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_height)],
            ASK_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_weight)],
            ASK_GOAL: [MessageHandler(filters.Regex(r'^(Набір маси|Схуднення|Підтримання|🔙 Назад)$') | (filters.TEXT & ~filters.COMMAND), profile_goal)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 Назад$'), cancel_profile)]
    )
    app.add_handler(conv)

    # Conversation для зміни цілі
    change_goal_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^🎯 Змінити мету$'), change_goal_start)],
        states={
            CHANGE_GOAL: [MessageHandler(filters.Regex(r'^(Набір маси|Схуднення|Підтримання|🔙 Назад)$') | (filters.TEXT & ~filters.COMMAND), change_goal_save)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 Назад$'), cancel_change_goal)]
    )
    app.add_handler(change_goal_conv)

    # Conversation для нагадувань
    remind_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^⏰ Нагадування$'), remind_start)],
        states={
            ASK_REMIND_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_ask_date)],
            ASK_REMIND_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_ask_time)],
            ASK_REMIND_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, remind_ask_text)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 Назад$'), cancel_reminder)]
    )
    app.add_handler(remind_conv)

    # Conversation для прогресу - вага
    weight_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^⚖️ Вага$'), track_weight)],
        states={
            WEIGHT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight_input)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 До вибору прогресу$'), progress_menu)]
    )
    app.add_handler(weight_conv)

    # Conversation для прогресу - заміри
    measurements_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^📏 Заміри$'), track_measurements)],
        states={
            MEASUREMENTS_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_measurements_input)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 До вибору прогресу$'), progress_menu)]
    )
    app.add_handler(measurements_conv)

    # Conversation для прогресу - тренування (ОНОВЛЕНИЙ)
    workout_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^💪 Тренування$'), track_workout)],
        states={
            WORKOUT_EXERCISE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workout_exercise)],
            WORKOUT_SETS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workout_sets)],
            WORKOUT_REPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workout_reps)],
            WORKOUT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workout_weight)],
            WORKOUT_CONTINUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_workout_continue)],
        },
        fallbacks=[MessageHandler(filters.Regex(r'^🔙 До вибору прогресу$'), progress_menu)]
    )
    app.add_handler(workout_conv)

    # Команди бота
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("callback", callback_command))
    app.add_handler(CommandHandler("create", create_command))
    app.add_handler(CommandHandler("calories", calories_command))
    app.add_handler(CommandHandler("plan", plan_command))
    app.add_handler(CommandHandler("statistics", statistics_command))
    
    # Обробник невідомих команд (повинен бути після всіх відомих команд)
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Обробник вибору групи м'язів (точно відповідає одній з груп)
    groups_pattern = r'^(?:' + '|'.join(re.escape(g) for g in muscle_groups) + r')$'
    app.add_handler(MessageHandler(filters.Regex(groups_pattern), exercises_group_selected))

    # Динамічний обробник для імен вправ: збираємо всі імена з БД
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM exercises")
    names = [row[0] for row in cur.fetchall()]
    conn.close()

    # Створюємо універсальний обробник для вправ
    async def universal_exercise_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        
        # Перевіряємо, чи знаходимося ми в режимі вправ
        if context.user_data.get('in_exercises'):
            # Перевіряємо, чи є текст назвою вправи
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM exercises WHERE name=?", (text,))
            exists = cur.fetchone()[0] > 0
            conn.close()
            
            if exists:
                return await exercise_detail(update, context)
        
        # Якщо не вправа, обробляємо як звичайне меню
        return await handle_menu_buttons(update, context)

    if names:
        # обмеження regex довжини: якщо дуже багато вправ, можна розбити — але для більшості випадків це ок.
        ex_pattern = r'^(?:' + '|'.join(re.escape(n) for n in names) + r')$'
        app.add_handler(MessageHandler(filters.Regex(ex_pattern), universal_exercise_handler))

    # Обробники "назад до списку" і т.п. -- спеціально обробляємо "🔙 Назад до списку" тут
    app.add_handler(MessageHandler(filters.Regex(r'^🔙 Назад до списку$'), back_to_exercise_list))

    # Обробник основних кнопок меню - ПОВИНЕН БУТИ ПІСЛЯ специфічних обробників
    app.add_handler(MessageHandler(filters.Regex(r'^(🏠 Головна|👤 Профіль|👀 Перегляд профілю|🎯 Змінити мету|🍎 Калорії|📅 План|💪 Вправи|📈 Прогрес|✅ Зберегти|❌ Не зберігати|📊 Статистика|🔙 До вибору прогресу)$'), handle_menu_buttons))

    # Обробник кнопки "🔙 Назад" - окремо, щоб не конфліктувати
    app.add_handler(MessageHandler(filters.Regex(r'^🔙 Назад$'), exercise_detail))

    # Всі інші текстові — невідомі (прибираємо group=10, щоб не блокувати інші обробники)
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text), group=10)

    logger.info("✅ Бота запущено...")
    
    # Встановлюємо команди для меню бота
    import asyncio
    from telegram import BotCommand
    
    async def set_commands():
        commands = [
            BotCommand("start", "Запустити бота/показати головне меню"),
            BotCommand("callback", "Зв'язок з розробником"),
            BotCommand("create", "Створити/редагувати профіль"),
            BotCommand("calories", "Калькулятор калорій"),
            BotCommand("plan", "План тренувань"),
            BotCommand("statistics", "Статистика прогресу")
        ]
        await app.bot.set_my_commands(commands)
        logger.info("✅ Команди бота встановлено")
    
    # Встановлюємо команди перед запуском
    asyncio.get_event_loop().run_until_complete(set_commands())
    
    app.run_polling(poll_interval=2)

if __name__ == "__main__":
    main()