#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🐱 Котик-планувальник для Telegram
Персональний помічник для планування подій та нагадувань
"""

import logging
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta, time
from typing import Optional, List
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# Логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Стани для розмов
ADDING_EVENT_NAME, ADDING_EVENT_DATE, ADDING_EVENT_TIME, ADDING_EVENT_DESC = range(4)
ADDING_BIRTHDAY_NAME, ADDING_BIRTHDAY_DATE = range(2)

# Котячі емодзі
CAT = {
    'happy': '😸', 'sleepy': '😴', 'excited': '🙀', 'heart': '😻',
    'wink': '😉', 'cool': '😎', 'thinking': '🤔', 'alarm': '⏰',
    'calendar': '📅', 'birthday': '🎂'
}

class CatPlannerBot:
    def __init__(self, token: str):
        self.token = token
        self.db_name = 'cat_planner.db'
        self.init_database()
        
        # Створюємо додаток
        self.app = Application.builder().token(token).build()
        
        # Налаштовуємо всі обробники
        self.setup_handlers()
    
    def init_database(self):
        """Створення бази даних"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Користувачі
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                timezone TEXT DEFAULT 'Europe/Kiev',
                morning_time TEXT DEFAULT '08:00',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Події
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                event_date DATE,
                event_time TIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Дні народження
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS birthdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                birth_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Фото розкладів
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_id TEXT,
                caption TEXT,
                photo_date DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def setup_handlers(self):
        """Налаштування всіх обробників"""
        
        # Основні команди
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        
        # Розмови для додавання
        event_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_add_event, pattern='^add_event$')],
            states={
                ADDING_EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_event_name)],
                ADDING_EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_event_date)],
                ADDING_EVENT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_event_time)],
                ADDING_EVENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_event)],
            },
            fallbacks=[CallbackQueryHandler(self.cancel, pattern='^cancel$')],
            per_message=False
        )
        
        birthday_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_add_birthday, pattern='^add_birthday$')],
            states={
                ADDING_BIRTHDAY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_birthday_name)],
                ADDING_BIRTHDAY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_birthday)],
            },
            fallbacks=[CallbackQueryHandler(self.cancel, pattern='^cancel$')],
            per_message=False
        )
        
        self.app.add_handler(event_conv)
        self.app.add_handler(birthday_conv)
        
        # Кнопки меню
        self.app.add_handler(CallbackQueryHandler(self.main_menu, pattern='^menu$'))
        self.app.add_handler(CallbackQueryHandler(self.today, pattern='^today$'))
        self.app.add_handler(CallbackQueryHandler(self.week, pattern='^week$'))
        self.app.add_handler(CallbackQueryHandler(self.my_events, pattern='^my_events$'))
        self.app.add_handler(CallbackQueryHandler(self.birthdays, pattern='^birthdays$'))
        self.app.add_handler(CallbackQueryHandler(self.settings, pattern='^settings$'))
        self.app.add_handler(CallbackQueryHandler(self.help, pattern='^help$'))
        self.app.add_handler(CallbackQueryHandler(self.photo_menu, pattern='^photos$'))
        self.app.add_handler(CallbackQueryHandler(self.my_photos, pattern='^my_photos$'))
        
        # Налаштування
        self.app.add_handler(CallbackQueryHandler(self.change_timezone_menu, pattern='^change_tz$'))
        self.app.add_handler(CallbackQueryHandler(self.change_time_menu, pattern='^change_time$'))
        self.app.add_handler(CallbackQueryHandler(self.set_timezone, pattern='^tz_'))
        self.app.add_handler(CallbackQueryHandler(self.set_time, pattern='^time_'))
        
        # Фото
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        
        # Текстові повідомлення
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def get_keyboard(self):
        """Головна клавіатура"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"{CAT['calendar']} Сьогодні", callback_data='today'),
                InlineKeyboardButton(f"{CAT['calendar']} Тиждень", callback_data='week')
            ],
            [
                InlineKeyboardButton("➕ Додати подію", callback_data='add_event'),
                InlineKeyboardButton(f"{CAT['birthday']} День народження", callback_data='add_birthday')
            ],
            [
                InlineKeyboardButton("📋 Мої події", callback_data='my_events'),
                InlineKeyboardButton(f"{CAT['birthday']} Іменинники", callback_data='birthdays')
            ],
            [
                InlineKeyboardButton("📷 Фото розкладу", callback_data='photos'),
                InlineKeyboardButton("⚙️ Налаштування", callback_data='settings')
            ],
            [
                InlineKeyboardButton("❓ Допомога", callback_data='help')
            ]
        ])
    
    # === ОСНОВНІ КОМАНДИ ===
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Початок роботи"""
        user = update.effective_user
        
        # Додаємо користувача в базу
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO users (user_id, first_name, username) VALUES (?, ?, ?)',
                      (user.id, user.first_name, user.username))
        conn.commit()
        conn.close()
        
        message = f"""
{CAT['heart']} Мяу! Привіт, {user.first_name}!

Я твій персональний котик-планувальник! {CAT['happy']}

Я допоможу тобі:
• {CAT['calendar']} Планувати події та завдання
• {CAT['alarm']} Нагадувати про важливі справи
• {CAT['birthday']} Не забувати про дні народження
• 📱 Зберігати фото розкладів
• 🌅 Надсилати ранковий план дня

Обери що хочеш зробити:
        """
        
        await update.message.reply_text(message, reply_markup=self.get_keyboard())
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Головне меню"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['happy']} Що будемо планувати?"
        await query.edit_message_text(message, reply_markup=self.get_keyboard())
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Допомога"""
        help_text = f"""
{CAT['thinking']} Ось що я вмію:

📅 **Планування подій:**
• Додавати події з датою та часом
• Переглядати розклад на день/тиждень
• Встановлювати нагадування

🎂 **Дні народження:**
• Додавати дні народження друзів
• Нагадувати о 00:00 про іменинників
• Показувати скільки років виповнюється

📷 **Фото розкладів:**
• Надсилай мені фото розкладу
• Я збережу їх і покажу коли потрібно
• Можна додавати підпис до фото

⏰ **Нагадування:**
• Ранкові нагадування (за замовчуванням о 8:00)
• Можна змінити час в налаштуваннях
• Нагадування про дні народження о півночі

{CAT['wink']} Просто натискай кнопки і я все зроблю!
        """
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='menu')]])
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(help_text, reply_markup=keyboard)
        else:
            await update.message.reply_text(help_text, reply_markup=keyboard)
    
    # === ДОДАВАННЯ ПОДІЙ ===
    
    async def start_add_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Початок додавання події"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['thinking']} Як назвемо подію? Напиши назву:"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data='cancel')]])
        await query.edit_message_text(message, reply_markup=keyboard)
        
        return ADDING_EVENT_NAME
    
    async def get_event_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отримуємо назву події"""
        context.user_data['event_name'] = update.message.text
        
        message = f"{CAT['calendar']} Чудово! Тепер вкажи дату.\n\nФормат: ДД.ММ.РРРР (наприклад: 25.12.2024)\nАбо напиши 'сьогодні' або 'завтра'"
        await update.message.reply_text(message)
        
        return ADDING_EVENT_DATE
    
    async def get_event_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отримуємо дату події"""
        date_text = update.message.text.lower().strip()
        
        try:
            if date_text == 'сьогодні':
                event_date = datetime.now().date()
            elif date_text == 'завтра':
                event_date = datetime.now().date() + timedelta(days=1)
            else:
                event_date = datetime.strptime(date_text, '%d.%m.%Y').date()
            
            context.user_data['event_date'] = event_date
            
            message = f"{CAT['alarm']} Вкажи час події.\n\nФормат: ГГ:ХХ (наприклад: 15:30)\nАбо напиши 'весь день'"
            await update.message.reply_text(message)
            
            return ADDING_EVENT_TIME
            
        except ValueError:
            await update.message.reply_text("Неправильний формат дати! Спробуй ще раз (наприклад: 25.12.2024)")
            return ADDING_EVENT_DATE
    
    async def get_event_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отримуємо час події"""
        time_text = update.message.text.lower().strip()
        
        if time_text == 'весь день':
            context.user_data['event_time'] = None
        else:
            try:
                event_time = datetime.strptime(time_text, '%H:%M').time()
                context.user_data['event_time'] = event_time
            except ValueError:
                await update.message.reply_text("Неправильний формат часу! Спробуй ще раз (наприклад: 15:30)")
                return ADDING_EVENT_TIME
        
        message = f"{CAT['thinking']} Додай опис події (необов'язково):\n\nАбо напиши 'пропустити'"
        await update.message.reply_text(message)
        
        return ADDING_EVENT_DESC
    
    async def save_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Зберігаємо подію"""
        description = update.message.text.strip()
        if description.lower() == 'пропустити':
            description = None
        
        # Зберігаємо в базу
        user_id = update.effective_user.id
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (user_id, title, description, event_date, event_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, context.user_data['event_name'], description,
              context.user_data['event_date'], context.user_data['event_time']))
        conn.commit()
        conn.close()
        
        # Готуємо повідомлення
        event_date = context.user_data['event_date']
        event_time = context.user_data['event_time']
        time_str = event_time.strftime('%H:%M') if event_time else 'Весь день'
        
        message = f"""
{CAT['excited']} Чудово! Подія додана:

📅 **{context.user_data['event_name']}**
🗓 Дата: {event_date.strftime('%d.%m.%Y')}
🕐 Час: {time_str}
{f"📝 Опис: {description}" if description else ""}

{CAT['wink']} Я не забуду нагадати тобі!
        """
        
        await update.message.reply_text(message, reply_markup=keyboard)
    
    async def my_photos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мої збережені фото"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        # Отримуємо фото з бази
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT file_id, caption, photo_date FROM photos WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
                      (user_id,))
        photos = cursor.fetchall()
        conn.close()
        
        if photos:
            # Надсилаємо фото одне за одним
            for file_id, caption, photo_date in photos:
                try:
                    date_str = datetime.strptime(photo_date, '%Y-%m-%d').strftime('%d.%m.%Y')
                    photo_caption = f"📅 Збережено: {date_str}\n"
                    if caption:
                        photo_caption += f"📝 {caption}"
                    
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=file_id,
                        caption=photo_caption
                    )
                except Exception as e:
                    logger.error(f"Помилка відправки фото: {e}")
            
            message = f"{CAT['excited']} Ось твої збережені фото розкладів!"
        else:
            message = f"{CAT['sleepy']} У тебе поки немає збережених фото"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📷 Додати фото", callback_data='photos')],
            [InlineKeyboardButton("« Назад", callback_data='menu')]
        ])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    # === НАЛАШТУВАННЯ ===
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Налаштування"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        # Отримуємо поточні налаштування
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT timezone, morning_time FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        timezone, morning_time = result if result else ('Europe/Kiev', '08:00')
        
        message = f"""
{CAT['cool']} Налаштування:

🌍 Часовий пояс: {timezone}
⏰ Ранкові нагадування: {morning_time}

{CAT['thinking']} Що хочеш змінити?
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌍 Змінити часовий пояс", callback_data='change_tz')],
            [InlineKeyboardButton("⏰ Змінити час нагадувань", callback_data='change_time')],
            [InlineKeyboardButton("« Назад", callback_data='menu')]
        ])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def change_timezone_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню зміни часового поясу"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['thinking']} Обери часовий пояс:"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇺🇦 Київ", callback_data='tz_Europe/Kiev')],
            [InlineKeyboardButton("🇵🇱 Варшава", callback_data='tz_Europe/Warsaw')],
            [InlineKeyboardButton("🇩🇪 Берлін", callback_data='tz_Europe/Berlin')],
            [InlineKeyboardButton("🇬🇧 Лондон", callback_data='tz_Europe/London')],
            [InlineKeyboardButton("🇺🇸 Нью-Йорк", callback_data='tz_America/New_York')],
            [InlineKeyboardButton("« Назад", callback_data='settings')]
        ])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def change_time_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню зміни часу нагадувань"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['alarm']} Обери час ранкових нагадувань:"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 07:00", callback_data='time_07:00')],
            [InlineKeyboardButton("☀️ 08:00", callback_data='time_08:00')],
            [InlineKeyboardButton("🌞 09:00", callback_data='time_09:00')],
            [InlineKeyboardButton("📚 10:00", callback_data='time_10:00')],
            [InlineKeyboardButton("❌ Вимкнути", callback_data='time_disabled')],
            [InlineKeyboardButton("« Назад", callback_data='settings')]
        ])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def set_timezone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Встановлення часового поясу"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        # Витягуємо часовий пояс
        timezone = query.data.replace('tz_', '')
        
        # Оновлюємо в базі
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET timezone = ? WHERE user_id = ?', (timezone, user_id))
        conn.commit()
        conn.close()
        
        message = f"""
{CAT['excited']} Часовий пояс змінено!

🌍 Новий часовий пояс: {timezone}

{CAT['wink']} Тепер всі нагадування будуть за твоїм часом!
        """
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад до налаштувань", callback_data='settings')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def set_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Встановлення часу нагадувань"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        # Витягуємо часовий пояс
        timezone = query.data.replace('tz_', '')
        
        # Оновлюємо в базі
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET timezone = ? WHERE user_id = ?', (timezone, user_id))
        conn.commit()
        conn.close()
        
        message = f"""
{CAT['excited']} Часовий пояс змінено!

🌍 Новий часовий пояс: {timezone}

{CAT['wink']} Тепер всі нагадування будуть за твоїм часом!
        """
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад до налаштувань", callback_data='settings')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def set_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Встановлення часу нагадувань"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        # Витягуємо час
        time_setting = query.data.replace('time_', '')
        
        # Оновлюємо в базі
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET morning_time = ? WHERE user_id = ?', (time_setting, user_id))
        conn.commit()
        conn.close()
        
        if time_setting == 'disabled':
            message = f"""
{CAT['sleepy']} Ранкові нагадування вимкнено!

Можеш увімкнути їх знову в налаштуваннях.
            """
        else:
            message = f"""
{CAT['alarm']} Час нагадувань змінено!

⏰ Новий час: {time_setting}

{CAT['heart']} Щоранку о {time_setting} я надсилатиму план дня!
            """
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад до налаштувань", callback_data='settings')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    # === ІНШІ ОБРОБНИКИ ===
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Скасування операції"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['wink']} Окей, скасовуємо! Що ще будемо робити?"
        await query.edit_message_text(message, reply_markup=self.get_keyboard())
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обробка текстових повідомлень"""
        text = update.message.text.lower()
        
        # Якщо користувач пише про розклад
        if any(word in text for word in ['розклад', 'план', 'що сьогодні', 'що завтра', 'справи']):
            await self.quick_schedule(update, context)
        else:
            # Відповідаємо мило
            responses = [
                f"{CAT['thinking']} Мяу? Не зрозумів... Спробуй натиснути кнопку!",
                f"{CAT['wink']} Котики краще розуміють кнопки! Тисни на меню!",
                f"{CAT['happy']} Мур-мур! Використай кнопки, так простіше!",
                f"{CAT['sleepy']} *потягується* Кнопки... люблю кнопки..."
            ]
            
            import random
            message = random.choice(responses)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Головне меню", callback_data='menu')]])
            await update.message.reply_text(message, reply_markup=keyboard)
    
    async def quick_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Швидкий показ розкладу"""
        user_id = update.effective_user.id
        today = datetime.now().date()
        
        # Події
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT title, event_time FROM events WHERE user_id = ? AND event_date = ? ORDER BY event_time',
                      (user_id, today))
        events = cursor.fetchall()
        
        # Дні народження
        cursor.execute('SELECT name FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                      (today,))
        birthdays = cursor.fetchall()
        conn.close()
        
        message = f"{CAT['calendar']} Ось що у нас сьогодні:\n\n"
        
        if birthdays:
            message += f"{CAT['birthday']} Дні народження:\n"
            for (name,) in birthdays:
                message += f"🎉 {name}\n"
            message += "\n"
        
        if events:
            message += f"{CAT['excited']} Події:\n"
            for title, time_str in events:
                time_display = datetime.strptime(time_str, '%H:%M:%S').strftime('%H:%M') if time_str else 'Весь день'
                message += f"• {time_display} - {title}\n"
        else:
            message += f"{CAT['sleepy']} Сьогодні подій не заплановано!"
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ Додати подію", callback_data='add_event'),
                InlineKeyboardButton("📅 Тиждень", callback_data='week')
            ],
            [InlineKeyboardButton("🏠 Головне меню", callback_data='menu')]
        ])
        await update.message.reply_text(message, reply_markup=keyboard)
    
    # === НАГАДУВАННЯ ===
    
    async def morning_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Ранкові нагадування"""
        current_time = datetime.now().time()
        
        # Отримуємо користувачів які хочуть нагадування зараз
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id FROM users 
            WHERE morning_time = ? AND morning_time != 'disabled'
        ''', (current_time.strftime('%H:%M'),))
        users = cursor.fetchall()
        
        today = datetime.now().date()
        
        for (user_id,) in users:
            try:
                # Події
                cursor.execute('SELECT title, event_time FROM events WHERE user_id = ? AND event_date = ? ORDER BY event_time',
                              (user_id, today))
                events = cursor.fetchall()
                
                # Дні народження
                cursor.execute('SELECT name, birth_date FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                              (today,))
                birthdays = cursor.fetchall()
                
                message = f"""
{CAT['alarm']} Доброго ранку!

{CAT['calendar']} План на сьогодні ({today.strftime('%d.%m.%Y')}):
"""
                
                if birthdays:
                    message += f"\n{CAT['birthday']} Дні народження:\n"
                    for name, birth_str in birthdays:
                        birth_date = datetime.strptime(birth_str, '%Y-%m-%d').date()
                        age = today.year - birth_date.year
                        message += f"🎉 {name} ({age} років)\n"
                
                if events:
                    message += f"\n{CAT['excited']} Твої події:\n"
                    for title, time_str in events:
                        time_display = datetime.strptime(time_str, '%H:%M:%S').strftime('%H:%M') if time_str else 'Весь день'
                        message += f"• {time_display} - {title}\n"
                
                if not events and not birthdays:
                    message += f"\n{CAT['sleepy']} Сьогодні вільний день! Можна відпочити"
                
                message += f"\n{CAT['heart']} Гарного дня!"
                
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📅 Детальніше", callback_data='today')]])
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=keyboard
                )
                
            except Exception as e:
                logger.error(f"Помилка відправки ранкового нагадування: {e}")
        
        conn.close()
    
    async def birthday_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Нагадування про дні народження о півночі"""
        current_time = datetime.now().time()
        
        # Перевіряємо чи зараз близько 00:00
        if current_time.hour == 0 and current_time.minute < 5:
            today = datetime.now().date()
            
            # Знаходимо всіх іменинників
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('SELECT name, birth_date FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                          (today,))
            birthdays = cursor.fetchall()
            
            if birthdays:
                # Отримуємо всіх користувачів
                cursor.execute('SELECT user_id FROM users')
                users = cursor.fetchall()
                
                message = f"""
{CAT['birthday']} УВАГА! Сьогодні день народження!

🎉 Іменинники:
"""
                
                for name, birth_str in birthdays:
                    birth_date = datetime.strptime(birth_str, '%Y-%m-%d').date()
                    age = today.year - birth_date.year
                    message += f"🎂 {name} ({age} років)\n"
                
                message += f"\n{CAT['heart']} Не забудь привітати!"
                
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Ідеї подарунків", url="https://www.google.com/search?q=ідеї+подарунків")]])
                
                for (user_id,) in users:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=keyboard
                        )
                    except Exception as e:
                        logger.error(f"Помилка відправки нагадування про день народження: {e}")
            
            conn.close()
    
    # === ЗАПУСК БОТА ===
    
    def run(self):
        """Запуск бота"""
        print(f"{CAT['excited']} Котик-планувальник запускається...")
        
        try:
            # Спроба додати job queue для нагадувань
            if self.app.job_queue:
                # Ранкові нагадування щохвилини
                self.app.job_queue.run_repeating(self.morning_reminder, interval=60, first=10)
                
                # Нагадування про дні народження кожні 5 хвилин о півночі
                self.app.job_queue.run_repeating(self.birthday_reminder, interval=300, first=10)
                
                print(f"{CAT['alarm']} Нагадування увімкнено!")
            else:
                print(f"{CAT['thinking']} JobQueue недоступний, працюємо без нагадувань")
            
            print(f"{CAT['happy']} Котик готовий до роботи!")
            self.app.run_polling()
            
        except Exception as e:
            logger.error(f"Помилка запуску: {e}")
            print(f"❌ Помилка: {e}")

# === ГОЛОВНА ФУНКЦІЯ ===

def main():
    # ВКАЖИ СВІЙ ТОКЕН ТУТ!
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ПОМИЛКА: Вкажи токен бота!")
        print()
        print("1. Створи бота через @BotFather в Telegram")
        print("2. Скопіюй токен")
        print("3. Замінь 'YOUR_BOT_TOKEN_HERE' на свій токен")
        print("4. Збережи файл і запусти знову")
        print()
        print("Приклад:")
        print('TOKEN = "1234567890:ABCdefGHIjklMNOpqrSTUvwxyz-1234567890"')
        return
    
    # Створюємо та запускаємо бота
    bot = CatPlannerBot(TOKEN)
    bot.run()

if __name__ == "__main__":
    main()
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # === ДНІ НАРОДЖЕННЯ ===
    
    async def start_add_birthday(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Початок додавання дня народження"""
        query = update.callback_query
        await query.answer()
        
        message = f"{CAT['birthday']} Як звати іменинника? Напиши ім'я:"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data='cancel')]])
        await query.edit_message_text(message, reply_markup=keyboard)
        
        return ADDING_BIRTHDAY_NAME
    
    async def get_birthday_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отримуємо ім'я іменинника"""
        context.user_data['birthday_name'] = update.message.text
        
        message = f"{CAT['calendar']} Коли день народження?\n\nФормат: ДД.ММ.РРРР (наприклад: 15.03.1995)"
        await update.message.reply_text(message)
        
        return ADDING_BIRTHDAY_DATE
    
    async def save_birthday(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Зберігаємо день народження"""
        date_text = update.message.text.strip()
        
        try:
            birth_date = datetime.strptime(date_text, '%d.%m.%Y').date()
            
            # Зберігаємо в базу
            user_id = update.effective_user.id
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO birthdays (user_id, name, birth_date) VALUES (?, ?, ?)',
                          (user_id, context.user_data['birthday_name'], birth_date))
            conn.commit()
            conn.close()
            
            today = datetime.now().date()
            age = today.year - birth_date.year
            if (today.month, today.day) < (birth_date.month, birth_date.day):
                age -= 1
            
            message = f"""
{CAT['birthday']} День народження додано!

🎉 **{context.user_data['birthday_name']}**
📅 Дата: {birth_date.strftime('%d.%m.%Y')}
🎂 Вік: {age} років

{CAT['heart']} Я нагадаю тобі о 00:00 в день народження!
            """
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад до меню", callback_data='menu')]])
            await update.message.reply_text(message, reply_markup=keyboard)
            
            context.user_data.clear()
            return ConversationHandler.END
            
        except ValueError:
            await update.message.reply_text("Неправильний формат дати! Спробуй ще раз (наприклад: 15.03.1995)")
            return ADDING_BIRTHDAY_DATE
    
    # === ПЕРЕГЛЯД ІНФОРМАЦІЇ ===
    
    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Розклад на сьогодні"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        today = datetime.now().date()
        
        # Події
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT title, description, event_time FROM events WHERE user_id = ? AND event_date = ? ORDER BY event_time',
                      (user_id, today))
        events = cursor.fetchall()
        
        # Дні народження
        cursor.execute('SELECT name, birth_date FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                      (today,))
        birthdays = cursor.fetchall()
        conn.close()
        
        message = f"{CAT['calendar']} Розклад на сьогодні ({today.strftime('%d.%m.%Y')}):\n\n"
        
        if birthdays:
            message += f"{CAT['birthday']} Дні народження:\n"
            for name, birth_str in birthdays:
                birth_date = datetime.strptime(birth_str, '%Y-%m-%d').date()
                age = today.year - birth_date.year
                message += f"🎉 {name} ({age} років)\n"
            message += "\n"
        
        if events:
            message += f"{CAT['excited']} Події:\n"
            for title, description, time_str in events:
                time_display = datetime.strptime(time_str, '%H:%M:%S').strftime('%H:%M') if time_str else 'Весь день'
                message += f"• {time_display} - {title}\n"
                if description:
                    message += f"  {description}\n"
        else:
            message += f"{CAT['sleepy']} Поки ніяких подій немає. Час відпочити!"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='menu')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def week(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Розклад на тиждень"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        today = datetime.now().date()
        
        message = f"{CAT['calendar']} Розклад на тиждень:\n\n"
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        for i in range(7):
            date = today + timedelta(days=i)
            day_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
            day_name = day_names[date.weekday()]
            
            # Події
            cursor.execute('SELECT title, event_time FROM events WHERE user_id = ? AND event_date = ? ORDER BY event_time',
                          (user_id, date))
            events = cursor.fetchall()
            
            # Дні народження
            cursor.execute('SELECT name FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                          (date,))
            birthdays = cursor.fetchall()
            
            message += f"📅 **{day_name}, {date.strftime('%d.%m')}**\n"
            
            if birthdays:
                for (name,) in birthdays:
                    message += f"🎂 {name}\n"
            
            if events:
                for title, time_str in events:
                    time_display = datetime.strptime(time_str, '%H:%M:%S').strftime('%H:%M') if time_str else 'Весь день'
                    message += f"• {time_display} - {title}\n"
            
            if not events and not birthdays:
                message += f"{CAT['sleepy']} Вільний день\n"
            
            message += "\n"
        
        conn.close()
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='menu')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def my_events(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мої події"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT title, description, event_date, event_time FROM events WHERE user_id = ? ORDER BY event_date DESC, event_time DESC LIMIT 10',
                      (user_id,))
        events = cursor.fetchall()
        conn.close()
        
        message = f"{CAT['calendar']} Твої останні події:\n\n"
        
        if events:
            for title, description, date_str, time_str in events:
                date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')
                time_display = datetime.strptime(time_str, '%H:%M:%S').strftime('%H:%M') if time_str else 'Весь день'
                message += f"📅 {date} - {time_display}\n"
                message += f"📝 **{title}**\n"
                if description:
                    message += f"   {description}\n"
                message += "\n"
        else:
            message += f"{CAT['sleepy']} У тебе поки немає збережених подій"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='menu')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def birthdays(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Найближчі дні народження"""
        query = update.callback_query
        await query.answer()
        
        today = datetime.now().date()
        message = f"{CAT['birthday']} Найближчі дні народження:\n\n"
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        found = False
        for i in range(30):
            check_date = today + timedelta(days=i)
            cursor.execute('SELECT name, birth_date FROM birthdays WHERE strftime("%m-%d", birth_date) = strftime("%m-%d", ?)',
                          (check_date,))
            day_birthdays = cursor.fetchall()
            
            if day_birthdays:
                found = True
                if i == 0:
                    date_str = "Сьогодні"
                elif i == 1:
                    date_str = "Завтра"
                else:
                    day_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця", 'Субота', 'Неділя']
                    day_name = day_names[check_date.weekday()]
                    date_str = f"{check_date.strftime('%d.%m')} ({day_name})"
                
                message += f"📅 **{date_str}:**\n"
                for name, birth_str in day_birthdays:
                    birth_date = datetime.strptime(birth_str, '%Y-%m-%d').date()
                    age = check_date.year - birth_date.year
                    message += f"🎂 {name} ({age} років)\n"
                message += "\n"
        
        conn.close()
        
        if not found:
            message += f"{CAT['sleepy']} Найближчим часом днів народження немає"
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data='menu')]])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    # === ФОТО ===
    
    async def photo_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню фото"""
        query = update.callback_query
        await query.answer()
        
        message = f"""
{CAT['thinking']} Фото розкладу:

📷 Надішли мені фото розкладу, і я його збережу!
📝 Можеш додати підпис до фото
📅 Я запам'ятаю дату коли ти його надіслав

Просто надішли фото наступним повідомленням!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Мої фото", callback_data='my_photos')],
            [InlineKeyboardButton("« Назад", callback_data='menu')]
        ])
        await query.edit_message_text(message, reply_markup=keyboard)
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обробка фото"""
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Найбільше фото
        caption = update.message.caption or ""
        
        # Зберігаємо в базу
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO photos (user_id, file_id, caption) VALUES (?, ?, ?)',
                      (user_id, photo.file_id, caption))
        conn.commit()
        conn.close()
        
        message = f"""
{CAT['excited']} Фото розкладу збережено!

📷 Я запам'ятав твоє фото розкладу
{f"📝 Підпис: {caption}" if caption else ""}
📅 Дата: {datetime.now().strftime('%d.%m.%Y')}

{CAT['wink']} Тепер я можу показати його коли потрібно!
        """
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад до меню", callback_data='menu')]])
        await update.message.reply_text(message, reply_markup=keyboard)
