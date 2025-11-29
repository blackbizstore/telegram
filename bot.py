import os
import logging
import sqlite3
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "").strip()

# === РЕКЛАМА ===
AD_PRICES = {
    "ad1": 10, "ad2": 15, "ad3": 8, "ad4": 12, "ad5": 20,
    "ad6": 25, "ad7": 18, "ad8": 14, "ad9": 16, "ad10": 11,
    "ad11": 7, "ad12": 22
}

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

# === БАЗА ===
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            message_type TEXT,
            content TEXT,
            ad_type TEXT,
            ad_price REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            ad_type TEXT,
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

# === КРИПТОБОТ ===
def create_crypto_invoice(amount, description, user_id):
    if not CRYPTO_BOT_TOKEN or len(CRYPTO_BOT_TOKEN) < 20:
        print("[ERROR] CRYPTO_BOT_TOKEN пустой или слишком короткий!")
        return None, None

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
        print(f"[DEBUG] CryptoBot response: {response.status_code} — {response.text}")
        if response.status_code == 200:
            result = response.json()
            if result.get('ok') and 'result' in result and 'pay_url' in result['result']:
                return result['result']['invoice_id'], result['result']['pay_url']
        return None, None
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        return None, None

# === ОБРАБОТЧИК КНОПОК — С ПЕРВЫМ "BACK" ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # === САМОЕ ПЕРВОЕ — КНОПКА НАЗАД ===
    if query.data == 'back':
        await start(query, context)
        return  # ← критично

    user = query.from_user
    if query.data == 'feedback':
        await query.edit_message_text("Напишите ваше сообщение:")
        context.user_data['mode'] = 'feedback'

    elif query.data == 'ad_menu':
        keyboard = [[InlineKeyboardButton(f"{AD_TYPES[k]} — ${AD_PRICES[k]}", callback_data=k)] for k in AD_TYPES]
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data='back')])
        await query.edit_message_text("Выберите рекламу:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in AD_TYPES:
        ad_key = query.data
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        keyboard = [
            [InlineKeyboardButton("💳 Криптобот", callback_data=f'crypto_{ad_key}')],
            [InlineKeyboardButton("👤 Админ", callback_data=f'admin_{ad_key}')],
            [InlineKeyboardButton("◀ Назад", callback_data='back')]
        ]
        await query.edit_message_text(
            f"🎯 {ad_name}\n💰 ${ad_price}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith('admin_'):
        ad_key = query.data.replace('admin_', '')
        ad_name = AD_TYPES[ad_key]
        context.user_data['mode'] = f'ad_order_{ad_key}'
        await query.edit_message_text(f"🎯 {ad_name}\nНапишите детали заказа:")

    elif query.data.startswith('crypto_'):
        ad_key = query.data.replace('crypto_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        invoice_id, payment_url = create_crypto_invoice(ad_price, f"Заказ: {ad_name}", user.id)
        if invoice_id and payment_url:
            await query.edit_message_text(
                f"✅ [Оплатить ${ad_price}]({payment_url})",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Ошибка. Напишите админу.")
    else:
        await query.edit_message_text("Неизвестная команда.")

# === ГЛАВНОЕ МЕНЮ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Обратная связь", callback_data='feedback')],
        [InlineKeyboardButton("📢 Реклама", callback_data='ad_menu')],
        [InlineKeyboardButton("📋 История", callback_data='history')],
        [InlineKeyboardButton("🛒 Заказы", callback_data='orders')]
    ]
    text = "🚀 Привет! Выберите:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# === ОБРАТНАЯ СВЯЗЬ + ОТВЕТ АДМИНА ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    username = user.username or 'N/A'

    # === ОТВЕТ АДМИНА ПОЛЬЗОВАТЕЛЮ ===
    if update.effective_user.id == ADMIN_CHAT_ID and update.message.reply_to_message:
        orig_msg = update.message.reply_to_message.text
        if "(ID:" in orig_msg:
            try:
                user_id = int(orig_msg.split("(ID:")[1].split(")")[0].strip())
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"💬 Админ ответил:\n\n{text}"
                )
                await update.message.reply_text("✅ Ответ отправлен!")
            except Exception as e:
                await update.message.reply_text(f"❌ Не удалось отправить: {e}")
        return

    # === ОБРАТНАЯ СВЯЗЬ ОТ ПОЛЬЗОВАТЕЛЯ ===
    if context.user_data.get('mode') == 'feedback':
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📩 @{username} (ID: {user.id}):\n\n{text}"
        )
        await update.message.reply_text("✅ Отправлено!")
        context.user_data['mode'] = None

    # === ЗАКАЗ РЕКЛАМЫ ===
    elif context.user_data.get('mode', '').startswith('ad_order_'):
        ad_key = context.user_data['mode'].replace('ad_order_', '')
        ad_name = AD_TYPES[ad_key]
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🛒 Заказ от @{username} (ID: {user.id}):\n{ad_name}\n{text}"
        )
        await update.message.reply_text("✅ Заказ отправлен!")
        context.user_data['mode'] = None

# === ЗАПУСК ===
def main():
    if not TOKEN or not CRYPTO_BOT_TOKEN:
        raise ValueError("Отсутствуют TELEGRAM_BOT_TOKEN или CRYPTO_BOT_TOKEN")
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
