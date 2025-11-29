import os
import logging
import sqlite3
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# === НАСТРОЙКИ — ИСПОЛЬЗУЮТ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ RAILWAY ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")

# === ЦЕНЫ И ТИПЫ РЕКЛАМЫ (12 видов) ===
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

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id INTEGER PRIMARY KEY,
            reply_to_admin BOOLEAN DEFAULT 0
        )
    ''')
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
        CREATE SELECT IF NOT EXISTS orders (
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

# === ЛОГИРОВАНИЕ СООБЩЕНИЙ ===
def save_message(user_id, username, first_name, message_type, content, ad_type=None, ad_price=None):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (user_id, username, first_name, message_type, content, ad_type, ad_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, message_type, content, ad_type, ad_price))
    conn.commit()
    conn.close()

# === СОЗДАНИЕ ИНВОЙСА ЧЕРЕЗ CRYPTO BOT API ===
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
            if result.get('ok') and 'result' in result:
                return result['result']['invoice_id'], result['result']['pay_url']
        return None, None
    except Exception as e:
        print(f"[CryptoBot Error] {e}")
        return None, None

# === КНОПКА НАЗАД — ГЕНЕРАТОР ===
def back_button(dest="main"):
    if dest == "ad_menu":
        return [[InlineKeyboardButton("◀ Назад", callback_data='back_to_ad_menu')]]
    else:
        return [[InlineKeyboardButton("◀ Назад", callback_data='back_to_main')]]

# === ОСНОВНОЕ МЕНЮ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Обратная связь", callback_data='feedback')],
        [InlineKeyboardButton("📢 Реклама", callback_data='ad_menu')],
        [InlineKeyboardButton("📋 Моя история", callback_data='history')],
        [InlineKeyboardButton("🛒 Мои заказы", callback_data='orders')]
    ]
    text = "🚀 Привет! Выберите:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# === ОБРАБОТЧИК КНОПОК ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # === КНОПКИ НАЗАД ===
    if query.data == 'back_to_main':
        await start(query, context)
        return
    elif query.data == 'back_to_ad_menu':
        keyboard = [[InlineKeyboardButton(f"{AD_TYPES[k]} - ${AD_PRICES[k]}", callback_data=k)] for k in AD_TYPES]
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data='back_to_main')])
        await query.edit_message_text("Выберите рекламу:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # === ОСТАЛЬНЫЕ КНОПКИ ===
    if query.data == 'feedback':
        await query.edit_message_text("Напишите ваше сообщение:")
        context.user_data['mode'] = 'feedback'

    elif query.data == 'ad_menu':
        keyboard = [[InlineKeyboardButton(f"{AD_TYPES[k]} - ${AD_PRICES[k]}", callback_data=k)] for k in AD_TYPES]
        keyboard.append([InlineKeyboardButton("◀ Назад", callback_data='back_to_main')])
        await query.edit_message_text("Выберите рекламу:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in AD_TYPES:
        ad_key = query.data
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        keyboard = [
            [InlineKeyboardButton("💳 Криптобот", callback_data=f'crypto_{ad_key}')],
            [InlineKeyboardButton("👤 Написать админу", callback_data=f'admin_{ad_key}')],
            [InlineKeyboardButton("◀ Назад", callback_data='back_to_ad_menu')]
        ]
        await query.edit_message_text(
            f"🎯 {ad_name}\n💰 ${ad_price}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data.startswith('admin_'):
        ad_key = query.data.replace('admin_', '')
        ad_name = AD_TYPES[ad_key]
        await query.edit_message_text(
            f"🎯 {ad_name}\nНапишите сообщение админу:",
            reply_markup=InlineKeyboardMarkup(back_button("ad_menu"))
        )
        context.user_data['mode'] = f'ad_order_{ad_key}'

    elif query.data.startswith('crypto_'):
        ad_key = query.data.replace('crypto_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        invoice_id, payment_url = create_crypto_invoice(ad_price, f"Заказ: {ad_name}", user.id)
        if invoice_id and payment_url:
            # Здесь можно сохранить заказ в базу, если нужно
            await query.edit_message_text(
                f"✅ Счёт на ${ad_price}\n[Оплатить]({payment_url})",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(back_button("ad_menu"))
            )
        else:
            await query.edit_message_text(
                "❌ Не удалось создать счёт.\nПроверьте токен CryptoBot и повторите попытку.",
                reply_markup=InlineKeyboardMarkup(back_button("ad_menu"))
            )

    elif query.data in ('history', 'orders'):
        await query.edit_message_text("Функция доступна по запросу.", reply_markup=InlineKeyboardMarkup(back_button()))

# === ОБРАТНАЯ СВЯЗЬ + ОТВЕТ АДМИНА ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    username = user.username or 'N/A'

    # Ответ админа пользователю
    if update.effective_user.id == ADMIN_CHAT_ID and update.message.reply_to_message:
        orig_msg = update.message.reply_to_message
        target_user_id = int(orig_msg.text.split()[2])  # извлечение ID из сообщения вида "Ответ пользователю (ID: 123456789):"
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"💬 Админ ответил:\n\n{text}"
            )
            await update.message.reply_text("✅ Ответ отправлен!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отправки: {e}")
        return

    # Обратная связь от пользователя
    if context.user_data.get('mode') == 'feedback':
        save_message(user.id, username, user.first_name, "Обратная связь", text)
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📩 Ответ пользователю (ID: {user.id}):\n\n{text}",
            reply_to_message_id=update.message.message_id
        )
        await update.message.reply_text("✅ Отправлено!", reply_markup=InlineKeyboardMarkup(back_button()))
        context.user_data['mode'] = None

    # Заказ рекламы
    elif context.user_data.get('mode', '').startswith('ad_order_'):
        ad_key = context.user_data['mode'].replace('ad_order_', '')
        ad_name = AD_TYPES[ad_key]
        ad_price = AD_PRICES[ad_key]
        save_message(user.id, username, user.first_name, "Заказ рекламы", text, ad_name, ad_price)
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🛒 Заказ: {ad_name} — ${ad_price}\nОт: @{username} (ID: {user.id})\n\n{text}"
        )
        await update.message.reply_text("✅ Заказ отправлен админу!", reply_markup=InlineKeyboardMarkup(back_button()))
        context.user_data['mode'] = None

# === ОСНОВНОЙ ЗАПУСК ===
def main():
    if not all([TOKEN, CRYPTO_BOT_TOKEN]):
        raise ValueError("Отсутствуют TELEGRAM_BOT_TOKEN или CRYPTO_BOT_TOKEN")
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
