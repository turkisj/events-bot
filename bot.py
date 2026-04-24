import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
CHOOSING_EVENT, CHOOSING_ROLE, ENTERING_CITY, ENTERING_PHONE = range(4)

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open("Events Data")
    return sheet

def get_events():
    sheet = get_sheet()
    ws = sheet.worksheet("events")
    records = ws.get_all_records()
    return [r for r in records if str(r.get("status", "")).strip().lower() == "open"]

def add_booking(data: dict):
    sheet = get_sheet()
    ws = sheet.worksheet("bookings")
    all_rows = ws.get_all_values()
    next_id = len(all_rows)
    ws.append_row([
        next_id,
        data["event_id"],
        data["username"],
        data["chat_id"],
        data["role"],
        data["from_city"],
        data["phone"],
        "confirmed",
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ])

def update_seats(event_id, role):
    sheet = get_sheet()
    ws = sheet.worksheet("events")
    records = ws.get_all_records()
    for i, row in enumerate(records):
        if str(row["id"]) == str(event_id):
            row_num = i + 2
            if role == "driver":
                current = int(row.get("driver_booked", 0))
                ws.update_cell(row_num, 10, current + 1)
            else:
                current = int(row.get("booked", 0))
                ws.update_cell(row_num, 9, current + 1)
                total = int(row.get("total_seats", 0))
                if current + 1 >= total:
                    ws.update_cell(row_num, 11, "full")
            break

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎟 الفعاليات المتاحة", callback_data="events")],
        [InlineKeyboardButton("📋 حجوزاتي", callback_data="mybookings")],
    ]
    await update.message.reply_text(
        "👋 أهلاً بك في *Diz Events*!\n\nمنصة الفعاليات مع خدمة النقل الذكي 🚗🏟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    events = get_events()
    if not events:
        text = "❌ لا توجد فعاليات متاحة حالياً"
        if query:
            await query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END

    keyboard = []
    for e in events:
        remaining = int(e.get("total_seats", 0)) - int(e.get("booked", 0))
        label = f"{e['title']} | {e['date']} | {e['price']} ريال | {remaining} مقاعد"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"event_{e['id']}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    
    if query:
        await query.edit_message_text("🎟 اختر الفعالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("🎟 اختر الفعالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return CHOOSING_EVENT

async def choose_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    event_id = query.data.replace("event_", "")
    context.user_data["event_id"] = event_id
    
    events = get_events()
    event = next((e for e in events if str(e["id"]) == event_id), None)
    if not event:
        await query.edit_message_text("❌ الفعالية غير متاحة")
        return ConversationHandler.END
    
    context.user_data["event"] = event
    
    info = (
        f"🎟 *{event['title']}*\n"
        f"📅 {event['date']}\n"
        f"📍 {event['venue']} — {event['city']}\n"
        f"💰 {event['price']} ريال للراكب\n"
        f"🚗 السائق: تذكرة مجانية!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🧍 راكب", callback_data="role_passenger")],
        [InlineKeyboardButton("🚗 سائق (تذكرة مجانية)", callback_data="role_driver")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="events")],
    ]
    
    await query.edit_message_text(info, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_ROLE

async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    role = query.data.replace("role_", "")
    context.user_data["role"] = role
    
    await query.edit_message_text("📍 من أي مدينة ستنطلق؟\n\nاكتب اسم المدينة:")
    return ENTERING_CITY

async def enter_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_city"] = update.message.text.strip()
    await update.message.reply_text("📱 أدخل رقم جوالك:")
    return ENTERING_PHONE

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user = update.effective_user
    event = context.user_data["event"]
    role = context.user_data["role"]
    
    booking_data = {
        "event_id": context.user_data["event_id"],
        "username": user.username or user.first_name,
        "chat_id": user.id,
        "role": role,
        "from_city": context.user_data["from_city"],
        "phone": phone,
    }
    
    try:
        add_booking(booking_data)
        update_seats(context.user_data["event_id"], role)
        
        role_text = "🚗 سائق (تذكرة مجانية)" if role == "driver" else "🧍 راكب"
        msg = (
            f"✅ *تم الحجز بنجاح!*\n\n"
            f"🎟 {event['title']}\n"
            f"📅 {event['date']}\n"
            f"📍 {event['venue']}\n"
            f"👤 {role_text}\n"
            f"🏙 الانطلاق من: {context.user_data['from_city']}\n\n"
            f"سيتم التواصل معك قريباً بتفاصيل الرحلة ✨"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Booking error: {e}")
        await update.message.reply_text("❌ حدث خطأ، حاول مرة أخرى")
    
    return ConversationHandler.END

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    sheet = get_sheet()
    ws = sheet.worksheet("bookings")
    records = ws.get_all_records()
    
    user_bookings = [r for r in records if str(r.get("chat_id")) == str(user.id)]
    
    if not user_bookings:
        text = "📋 ليس لديك حجوزات حالياً"
    else:
        lines = ["📋 *حجوزاتك:*\n"]
        for b in user_bookings[-5:]:
            lines.append(f"• {b.get('event_id')} | {b.get('role')} | {b.get('status')}")
        text = "\n".join(lines)
    
    if query:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎟 الفعاليات المتاحة", callback_data="events")],
        [InlineKeyboardButton("📋 حجوزاتي", callback_data="mybookings")],
    ]
    await query.edit_message_text(
        "👋 أهلاً بك في *Diz Events*!\n\nمنصة الفعاليات مع خدمة النقل الذكي 🚗🏟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء")
    return ConversationHandler.END

def main():
    token = os.environ.get("EVENTS_BOT_TOKEN")
    app = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(show_events, pattern="^events$")],
        states={
            CHOOSING_EVENT: [CallbackQueryHandler(choose_event, pattern="^event_")],
            CHOOSING_ROLE: [CallbackQueryHandler(choose_role, pattern="^role_")],
            ENTERING_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_city)],
            ENTERING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(my_bookings, pattern="^mybookings$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    
    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
