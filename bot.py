import os
import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# === Безопасные переменные из окружения ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")

# Цены на рекламу
AD_PRICES = {
    "ad1": 10, "ad2": 15, "ad3": 8, "ad4": 12, "ad5": 20,
    "ad6": 25, "ad7": 18, "ad8": 14, "ad9": 16, "ad10": 11,
    "ad11": 7, "ad12": 22
}

# Виды рекламы
AD_TYPES = {
    "ad1": "Баннер в шапке",
    "ad2": "Рекламный пост",
    "ad3": "Текст в чате",
    "ad4": "Реклама в новостях",
    "ad5": "Попап-баннер",
    "ad6": "Видео-реклама",
    "ad7": "Спонсорский пост",
    "ad8": "Реклама в профиле",
    "ad9": "Push-уведомления",
    "ad10": "Реклама в поиске",
    "ad11": "Текстовая ссылка",
    "ad12": "Реклама в статусе"
}

def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ad_name TEXT,
            amount REAL,
            payment_url TEXT,
            invoice_id TEXT,
            status TEXT DEFAULT 'pending',
            payment_method TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_order(user_id, username, ad_name, amount, payment_url, invoice_id, payment_method):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, username, ad_name, amount, payment_url, invoice_id, payment_method)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, ad_name, amount, payment_url, invoice_id, payment_method))
    conn.commit()
    conn.close()

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
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            return result['result']['invoice_id'], result['result']['pay_url']
        else:
            return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📢 Реклама", callback_data='ad_menu')],
        [InlineKeyboardButton("📝 Обратная связь", callback_data='feedback')]
    ]
    await update.message.reply_text("Привет! Выберите:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'feedback':
        await query.edit_message_text("Напишите ваше сообщение:")
        context.user_data['mode'] = 'feedback'
    elif query.data == 'ad_menu':
        keyboard = [[InlineKeyboardButton(f"{AD_TYPES[k]} - ${AD_PRICES[k]}", callback_data=k)] for k in AD_TYPES]
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data='back')])
        await query.edit_message_text("Выберите рекламу:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data in AD_TYPES:
        ad_key = query.data
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        keyboard = [
            [InlineKeyboardButton("💳 Криптобот", callback_data=f'crypto_{ad_key}')],
            [InlineKeyboardButton("◀ Назад", callback_data='ad_menu')]
        ]
        await query.edit_message_text(f"🎯 {ad_name}\n💰 ${ad_price}", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('crypto_'):
        ad_key = query.data.replace('crypto_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        user = query.from_user
        invoice_id, payment_url = create_crypto_invoice(ad_price, f"Заказ: {ad_name}", user.id)
        if invoice_id and payment_url:
            save_order(user.id, user.username or 'N/A', ad_name, ad_price, payment_url, invoice_id, 'CryptoBot')
            await query.edit_message_text(f"Оплатите:\n[→ {ad_name}]({payment_url})", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Ошибка. Напишите админу.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if context.user_data.get('mode') == 'feedback':
        await context.bot.send_message(ADMIN_CHAT_ID, f"📩 от @{user.username or user.first_name} ({user.id}):\n{text}")
        await update.message.reply_text("✅ Отправлено!")
        context.user_data['mode'] = None

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()