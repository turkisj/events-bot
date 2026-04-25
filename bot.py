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

CHOOSING_GENDER, CHOOSING_CITY, CHOOSING_TYPE, CHOOSING_TEAM, CHOOSING_EVENT, CHOOSING_ROLE, ENTERING_CITY, ENTERING_PHONE, CONFIRMING_PHONE = range(9)

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

CITIES = ["الرياض", "جدة", "المدينة المنورة", "مكة المكرمة", "الدمام", "أبها", "تبوك", "ينبع"]
EVENT_TYPES = {"football": "⚽ كرة قدم", "concert": "🎤 حفلات غنائية", "all": "🎯 الكل"}

TEAMS = [
    "النصر", "الهلال", "الأهلي", "القادسية",
    "التعاون", "الاتحاد", "الاتفاق", "نيوم",
    "الحزم", "الفيحاء", "الخليج", "الشباب",
    "الفتح", "الخلود", "ضمك", "الرياض",
    "الأخدود", "النجمة"
]

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open("Events Data")

def get_events(gender=None, event_city=None, event_type=None, team=None):
    sheet = get_sheet()
    ws = sheet.worksheet("events")
    records = ws.get_all_records()
    results = []
    for r in records:
        if str(r.get("status", "")).strip().lower() != "open":
            continue
        if gender and r.get("gender") not in [gender, "both"]:
            continue
        if event_city and r.get("event_city") != event_city:
            continue
        if event_type and event_type != "all" and r.get("type") != event_type:
            continue
        if team and team != "all":
            teams_in_event = [t.strip() for t in str(r.get("teams", "")).split(",")]
            if team not in teams_in_event:
                continue
        results.append(r)
    return results

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
        data.get("team_pref", ""),
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
                ws.update_cell(row_num, 11, current + 1)
            else:
                current = int(row.get("booked", 0))
                ws.update_cell(row_num, 9, current + 1)
                total = int(row.get("total_seats", 0))
                if current + 1 >= total:
                    ws.update_cell(row_num, 12, "full")
            break

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🎟 الفعاليات المتاحة", callback_data="events")],
        [InlineKeyboardButton("📋 حجوزاتي", callback_data="mybookings")],
    ]
    await update.message.reply_text(
        "👋 أهلاً بك في *Diz Events*!\n\nمنصة الفعاليات مع خدمة النقل الذكي 🚗🏟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("👨 ذكور", callback_data="gender_male")],
        [InlineKeyboardButton("👩 إناث", callback_data="gender_female")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
    ]
    await query.edit_message_text(
        "📌 *ملاحظة مهمة:*\n"
        "جميع الرحلات تشمل:\n"
        "✅ ذهاب وعودة\n"
        "✅ التذاكر مشمولة في السعر\n\n"
        "👤 اختر الجنس:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_GENDER

async def choose_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["gender"] = query.data.replace("gender_", "")
    keyboard = [[InlineKeyboardButton(city, callback_data=f"city_{city}")] for city in CITIES]
    keyboard.append([InlineKeyboardButton("🌍 كل المدن", callback_data="city_all")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="events")])
    await query.edit_message_text("📍 اختر مدينة الفعالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_CITY

async def choose_city_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    city = query.data.replace("city_", "")
    context.user_data["event_city"] = None if city == "all" else city
    keyboard = [
        [InlineKeyboardButton("⚽ كرة قدم", callback_data="type_football")],
        [InlineKeyboardButton("🎤 حفلات غنائية", callback_data="type_concert")],
        [InlineKeyboardButton("🎯 الكل", callback_data="type_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="events")],
    ]
    await query.edit_message_text("🎭 اختر نوع الفعالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_TYPE

async def choose_type_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_type = query.data.replace("type_", "")
    context.user_data["event_type"] = event_type

    if event_type == "football":
        keyboard = []
        row = []
        for i, team in enumerate(TEAMS):
            row.append(InlineKeyboardButton(team, callback_data=f"team_{team}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="events")])
        await query.edit_message_text("⚽ اختر ناديك المفضل:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CHOOSING_TEAM
    else:
        context.user_data["team_pref"] = ""
        return await show_filtered_events(update, context)

async def choose_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    team = query.data.replace("team_", "")
    context.user_data["team_pref"] = team
    return await show_filtered_events(update, context)

async def show_filtered_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        events = get_events(
            gender=context.user_data.get("gender"),
            event_city=context.user_data.get("event_city"),
            event_type=context.user_data.get("event_type"),
            team=context.user_data.get("team_pref")
        )
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        await query.edit_message_text(f"❌ خطأ في الاتصال بالبيانات:\n{str(e)}")
        return ConversationHandler.END

    if not events:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="events")]]
        await query.edit_message_text(
            "❌ لا توجد فعاليات متاحة بهذه المعايير",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END

    keyboard = []
    for e in events:
        remaining = int(e.get("total_seats", 0)) - int(e.get("booked", 0))
        type_label = EVENT_TYPES.get(e.get("type", ""), "🎟")
        label = f"{type_label} {e['title']} | {e['event_city']} | {e['price']} ريال | {remaining} مقاعد"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"event_{e['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="events")])
    await query.edit_message_text("🎟 اختر الفعالية:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_EVENT

async def choose_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = query.data.replace("event_", "")
    context.user_data["event_id"] = event_id

    try:
        all_events = get_events()
        event = next((e for e in all_events if str(e["id"]) == event_id), None)
        if not event:
            await query.edit_message_text("❌ الفعالية غير متاحة")
            return ConversationHandler.END
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)}")
        return ConversationHandler.END

    context.user_data["event"] = event
    type_label = EVENT_TYPES.get(event.get("type", ""), "🎟")
    team_pref = context.user_data.get("team_pref", "")
    team_line = f"⚽ ناديك المفضل: {team_pref}\n" if team_pref else ""

    info = (
        f"{type_label} *{event['title']}*\n"
        f"📅 {event['date']}\n"
        f"📍 {event['venue']} — {event['event_city']}\n"
        f"{team_line}"
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
    context.user_data["role"] = query.data.replace("role_", "")
    await query.edit_message_text("📍 من أي مدينة ستنطلق؟\n\nاكتب اسم المدينة:")
    return ENTERING_CITY

async def enter_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["from_city"] = update.message.text.strip()
    await update.message.reply_text("📱 أدخل رقم جوالك:")
    return ENTERING_PHONE

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not phone.startswith("05") or not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text(
            "❌ رقم الجوال غير صحيح\n\n"
            "تأكد أن الرقم:\n"
            "• يبدأ بـ 05\n"
            "• مكون من 10 أرقام\n\n"
            "أعد إدخال رقم الجوال:"
        )
        return ENTERING_PHONE

    context.user_data["phone_first"] = phone
    await update.message.reply_text("📱 أعد إدخال رقم الجوال للتأكيد:")
    return CONFIRMING_PHONE

async def confirm_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not phone.startswith("05") or not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text(
            "❌ رقم الجوال غير صحيح\n\n"
            "أعد إدخال رقم الجوال للتأكيد:"
        )
        return CONFIRMING_PHONE

    if phone != context.user_data.get("phone_first"):
        await update.message.reply_text(
            "❌ الرقمان غير متطابقان\n\n"
            "أعد إدخال رقم الجوال من البداية:"
        )
        context.user_data.pop("phone_first", None)
        return ENTERING_PHONE

    user = update.effective_user
    event = context.user_data["event"]
    role = context.user_data["role"]
    event_id = context.user_data["event_id"]
    team_pref = context.user_data.get("team_pref", "")

    try:
        sheet = get_sheet()
        ws = sheet.worksheet("events")
        records = ws.get_all_records()
        current_event = next((r for r in records if str(r["id"]) == str(event_id)), None)

        if not current_event:
            await update.message.reply_text("❌ الفعالية غير موجودة")
            return ConversationHandler.END

        if role == "driver":
            if int(current_event.get("driver_booked", 0)) >= 1:
                await update.message.reply_text("❌ تم حجز مقعد السائق مسبقاً")
                return ConversationHandler.END
        else:
            booked = int(current_event.get("booked", 0))
            total = int(current_event.get("total_seats", 0))
            if booked >= total:
                await update.message.reply_text("❌ عذراً، المقاعد امتلأت")
                return ConversationHandler.END

        booking_data = {
            "event_id": event_id,
            "username": user.username or user.first_name,
            "chat_id": user.id,
            "role": role,
            "from_city": context.user_data["from_city"],
            "phone": phone,
            "team_pref": team_pref,
        }

        add_booking(booking_data)
        update_seats(event_id, role)

        role_text = "🚗 سائق (تذكرة مجانية)" if role == "driver" else "🧍 راكب"
        team_line = f"⚽ ناديك: {team_pref}\n" if team_pref else ""
        msg = (
            f"✅ *تم الحجز بنجاح!*\n\n"
            f"🎟 {event['title']}\n"
            f"📅 {event['date']}\n"
            f"📍 {event['venue']}\n"
            f"👤 {role_text}\n"
            f"{team_line}"
            f"🏙 الانطلاق من: {context.user_data['from_city']}\n\n"
            f"سيتم التواصل معك قريباً بتفاصيل الرحلة ✨"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

        admin_id = int(os.environ.get("ADMIN_ID"))
        booked_count = int(current_event.get("booked", 0)) + (0 if role == "driver" else 1)
        driver_count = int(current_event.get("driver_booked", 0)) + (1 if role == "driver" else 0)
        total = int(current_event.get("total_seats", 0))

        admin_msg = (
            f"🔔 حجز جديد!\n\n"
            f"🎟 {event['title']}\n"
            f"📅 {event['date']}\n"
            f"👤 {'🚗 سائق' if role == 'driver' else '🧍 راكب'} — {user.username or user.first_name}\n"
            f"🏙 الانطلاق من: {context.user_data['from_city']}\n"
            f"📱 {phone}\n"
            f"⚽ النادي المفضل: {team_pref or 'غير محدد'}\n\n"
            f"📊 المقاعد: {booked_count}/{total} | سائق: {'✅' if driver_count >= 1 else '❌'}"
        )
        await context.bot.send_message(chat_id=admin_id, text=admin_msg)

        if booked_count >= total and driver_count >= 1:
            complete_msg = (
                f"✅ اكتملت السيارة!\n\n"
                f"🎟 {event['title']}\n"
                f"📅 {event['date']}\n"
                f"👥 السائق + {total} ركاب جاهزين 🎉"
            )
            await context.bot.send_message(chat_id=admin_id, text=complete_msg)

    except Exception as e:
        logger.error(f"Booking error: {e}")
        await update.message.reply_text("❌ حدث خطأ، حاول مرة أخرى")

    return ConversationHandler.END

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user = update.effective_user
    try:
        sheet = get_sheet()
        ws = sheet.worksheet("bookings")
        records = ws.get_all_records()
        user_bookings = [r for r in records if str(r.get("chat_id")) == str(user.id)]
    except Exception as e:
        if query:
            await query.edit_message_text(f"❌ خطأ: {str(e)}")
        return

    if not user_bookings:
        text = "📋 ليس لديك حجوزات حالياً"
    else:
        lines = ["📋 *حجوزاتك:*\n"]
        for b in user_bookings[-5:]:
            lines.append(f"• {b.get('event_id')} | {b.get('role')} | {b.get('status')}")
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back")]]
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
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
        entry_points=[CallbackQueryHandler(start_filter, pattern="^events$")],
        states={
            CHOOSING_GENDER: [CallbackQueryHandler(choose_gender, pattern="^gender_")],
            CHOOSING_CITY: [CallbackQueryHandler(choose_city_filter, pattern="^city_")],
            CHOOSING_TYPE: [CallbackQueryHandler(choose_type_filter, pattern="^type_")],
            CHOOSING_TEAM: [CallbackQueryHandler(choose_team, pattern="^team_")],
            CHOOSING_EVENT: [CallbackQueryHandler(choose_event, pattern="^event_")],
            CHOOSING_ROLE: [CallbackQueryHandler(choose_role, pattern="^role_")],
            ENTERING_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_city)],
            ENTERING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
            CONFIRMING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_phone)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(back, pattern="^back$"),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(my_bookings, pattern="^mybookings$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
