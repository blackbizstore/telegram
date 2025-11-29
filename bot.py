import os
import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# === БЕЗОПАСНЫЕ ПЕРЕМЕННЫЕ ИЗ ОКРУЖЕНИЯ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")

# Реклама и цены
AD_PRICES = {"ad1": 10, "ad2": 15, "ad3": 8, "ad4": 12, "ad5": 20}
AD_TYPES = {
    "ad1": "Баннер в шапке",
    "ad2": "Рекламный пост",
    "ad3": "Текст в чате",
    "ad4": "Реклама в новостях",
    "ad5": "Попап-баннер"
}

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ===
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # Все сообщения от пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            message_text TEXT,
            message_type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Заказы рекламы
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ad_name TEXT,
            amount REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Платежи через CryptoBot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crypto_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ad_name TEXT,
            amount REAL,
            invoice_id TEXT UNIQUE,
            payment_url TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            paid_at DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()

# === СОХРАНЕНИЕ ЛОГОВ ===
def log_message(user_id, username, first_name, text, msg_type="plain"):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO message_log (user_id, username, first_name, message_text, message_type)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, text, msg_type))
    conn.commit()
    conn.close()

def save_ad_order(user_id, username, ad_name, amount):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO ad_orders (user_id, username, ad_name, amount)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, ad_name, amount))
    conn.commit()
    conn.close()

def save_payment(user_id, username, ad_name, amount, invoice_id, payment_url):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO crypto_payments (user_id, username, ad_name, amount, invoice_id, payment_url)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, ad_name, amount, invoice_id, payment_url))
    conn.commit()
    conn.close()

def get_user_history(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT message_text, message_type, timestamp 
        FROM message_log WHERE user_id = ? ORDER BY timestamp ASC
    ''', (user_id,))
    messages = cursor.fetchall()
    
    cursor.execute('''
        SELECT ad_name, amount, timestamp 
        FROM ad_orders WHERE user_id = ? ORDER BY timestamp ASC
    ''', (user_id,))
    orders = cursor.fetchall()
    
    cursor.execute('''
        SELECT ad_name, amount, status, payment_url, created_at 
        FROM crypto_payments WHERE user_id = ? ORDER BY created_at ASC
    ''', (user_id,))
    payments = cursor.fetchall()
    
    conn.close()
    return {"messages": messages, "orders": orders, "payments": payments}

# === КРИПТОБОТ: СОЗДАНИЕ ИНВОЙСА ===
def create_crypto_invoice(amount, description, user_id):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {
        'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN,
        'Content-Type': 'application/json'
    }
    data = {
        "asset": "USDT",
        "amount": str(amount),
        "description": description,
        "paid_btn_name": "URL",
        "paid_btn_url": f"https://t.me/{user_id}"
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return result['result']['invoice_id'], result['result']['pay_url']
        return None, None
    except Exception as e:
        print(f"Ошибка при создании инвойса: {e}")
        return None, None

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Обратная связь", callback_data='feedback')],
        [InlineKeyboardButton("📢 Реклама", callback_data='ad_menu')],
        [InlineKeyboardButton("📋 Моя история", callback_data='my_history')]
    ]
    await update.message.reply_text("Привет! Выберите:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    if query.data == 'feedback':
        await query.edit_message_text("Напишите ваше сообщение:")
        context.user_data['mode'] = 'feedback'
    
    elif query.data == 'ad_menu':
        keyboard = [[InlineKeyboardButton(f"{AD_TYPES[k]} - ${AD_PRICES[k]}", callback_data=k)] for k in AD_TYPES]
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data='back')])
        await query.edit_message_text("Выберите рекламу:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data in AD_TYPES:
        ad_name = AD_TYPES[query.data]
        ad_price = AD_PRICES[query.data]
        keyboard = [
            [InlineKeyboardButton("💳 Криптобот", callback_data=f'crypto_{query.data}')],
            [InlineKeyboardButton("👤 Написать админу", callback_data=f'admin_{query.data}')],
            [InlineKeyboardButton("◀ Назад", callback_data='ad_menu')]
        ]
        await query.edit_message_text(f"🎯 {ad_name}\n💰 ${ad_price}", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith('admin_'):
        ad_key = query.data.replace('admin_', '')
        ad_name = AD_TYPES[ad_key]
        context.user_data['mode'] = f'ad_order_{ad_key}'
        await query.edit_message_text(f"Напишите админу о заказе '{ad_name}'")
    
    elif query.data.startswith('crypto_'):
        ad_key = query.data.replace('crypto_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        invoice_id, payment_url = create_crypto_invoice(ad_price, f"Реклама: {ad_name}", user.id)
        if invoice_id and payment_url:
            save_payment(user.id, user.username or 'N/A', ad_name, ad_price, invoice_id, payment_url)
            await query.edit_message_text(f"✅ Счёт создан!\n[Оплатить {ad_price} USDT]({payment_url})", parse_mode='Markdown')
            log_message(user.id, user.username, user.first_name, f"Оплатил {ad_name}", "payment")
        else:
            await query.edit_message_text("❌ Не удалось создать счёт. Напишите админу.")
    
    elif query.data == 'my_history':
        history = get_user_history(user.id)
        msg = "📋 Ваша история:\n\n"
        msg += "💬 Сообщения:\n" + "\n".join([f"- {h[0]} ({h[1]})" for h in history["messages"][-5:]]) + "\n\n"
        msg += "🛒 Заказы:\n" + "\n".join([f"- {h[0]} — ${h[1]}" for h in history["orders"][-5:]]) + "\n\n"
        msg += "💳 Платежи:\n" + "\n".join([f"- {h[0]} — ${h[1]} ({h[2]})" for h in history["payments"][-5:]])
        await query.edit_message_text(msg or "История пуста")
    
    elif query.data == 'back':
        await start(query, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    username = user.username or 'N/A'
    
    # Сохраняем ВСЕ сообщения
    log_message(user.id, username, user.first_name, text, "plain")
    
    if context.user_data.get('mode') == 'feedback':
        log_message(user.id, username, user.first_name, text, "feedback")
        await context.bot.send_message(ADMIN_CHAT_ID, f"📩 от @{username} (ID: {user.id}):\n{text}")
        await update.message.reply_text("✅ Отправлено!")
        context.user_data['mode'] = None
    
    elif context.user_data.get('mode', '').startswith('ad_order_'):
        ad_key = context.user_data['mode'].replace('ad_order_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        log_message(user.id, username, user.first_name, text, "ad_order")
        save_ad_order(user.id, username, ad_name, ad_price)
        await context.bot.send_message(ADMIN_CHAT_ID, f"🛒 Заказ от @{username}:\n{ad_name}\n{text}")
        await update.message.reply_text(f"✅ Заказ '{ad_name}' отправлен админу!")
        context.user_data['mode'] = None

# === ОСНОВНОЙ ЗАПУСК ===
def main():
    if not TELEGRAM_BOT_TOKEN or not CRYPTO_BOT_TOKEN:
        raise ValueError("Отсутствуют переменные окружения: TELEGRAM_BOT_TOKEN или CRYPTO_BOT_TOKEN")
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
