import os
import json
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
MAPS_API = os.environ.get("MAPS_API")
SAVED_FILE = "saved.json"

CATEGORIES = {
    "💈 Kirpyklos": "kirpykla",
    "🔧 Automechanikai": "autoservisas",
    "🍕 Restoranai": "restoranas",
    "☕ Kavinės": "kavinė",
    "🚿 Santechnikai": "santechnikas",
    "💅 Grožio salonai": "grožio salonas",
    "💪 Sporto klubai": "sporto klubas",
    "🏥 Odontologai": "odontologas",
    "🐾 Veterinarai": "veterinarija",
    "🧹 Valymo paslaugos": "valymo paslaugos",
}

CITIES = ["Vilnius", "Kaunas", "Klaipėda", "Šiauliai", "Panevėžys", "Alytus", "Marijampolė", "Mažeikiai", "Jonava", "Utena"]

def load_saved():
    try:
        with open(SAVED_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_business(place_id):
    saved = load_saved()
    if place_id not in saved:
        saved.append(place_id)
        with open(SAVED_FILE, "w") as f:
            json.dump(saved, f)

def search_businesses(keyword, city):
    saved = load_saved()
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"{keyword} {city} Lietuva",
        "key": MAPS_API,
        "language": "lt",
        "region": "lt"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
    except Exception as e:
        logger.error(f"Maps API error: {e}")
        return []

    results = []
    for place in data.get("results", []):
        place_id = place.get("place_id")
        if place_id in saved:
            continue
        if place.get("website"):
            continue

        detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
        detail_params = {
            "place_id": place_id,
            "fields": "name,formatted_phone_number,formatted_address,website",
            "key": MAPS_API
        }
        try:
            detail_resp = requests.get(detail_url, params=detail_params, timeout=10)
            detail = detail_resp.json().get("result", {})
        except:
            continue

        if detail.get("website"):
            continue

        phone = detail.get("formatted_phone_number", "")
        if not phone:
            continue

        results.append({
            "place_id": place_id,
            "name": place.get("name", ""),
            "phone": phone,
            "address": detail.get("formatted_address", ""),
        })

        if len(results) >= 10:
            break

    return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in CATEGORIES]
    await update.message.reply_text(
        "🤖 *WebsiteFinder Botas*\n\nRandu verslas be svetainės visoje Lietuvoje ir paruošiu SMS tekstą!\n\n📂 Pasirink kategoriją:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("cat|"):
        cat = data[4:]
        keyword = CATEGORIES.get(cat, cat)
        context.user_data["cat"] = cat
        context.user_data["keyword"] = keyword

        keyboard = []
        row = []
        for i, city in enumerate(CITIES):
            row.append(InlineKeyboardButton(city, callback_data=f"city|{city}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="back")])

        await query.edit_message_text(
            f"✅ Kategorija: *{cat}*\n\n🏙 Pasirink miestą:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("city|"):
        city = data[5:]
        keyword = context.user_data.get("keyword", "verslas")
        cat = context.user_data.get("cat", "")

        await query.edit_message_text(f"🔍 Ieškau *{cat}* mieste *{city}*...\n⏳ Palaukite kelias sekundes!", parse_mode="Markdown")

        businesses = search_businesses(keyword, city)
        context.user_data["businesses"] = businesses
        context.user_data["city"] = city

        if not businesses:
            keyboard = [
                [InlineKeyboardButton("🔄 Bandyti kitą miestą", callback_data=f"cat|{cat}")],
                [InlineKeyboardButton("🏠 Pradžia", callback_data="back")]
            ]
            await query.edit_message_text(
                f"😕 {city} nerasta verslų be svetainės kategorijoje *{cat}*.\n\nBandyk kitą miestą arba kategoriją!",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return

        await show_business(query, context, 0)

    elif data.startswith("sms|"):
        idx = int(data[4:])
        businesses = context.user_data.get("businesses", [])
        if idx >= len(businesses):
            return
        b = businesses[idx]
        name = b["name"]
        phone = b["phone"]
        sms = f"Sveiki! Pastebėjau kad {name} neturi interneto svetainės. Kuriu profesionalias svetaines už 50€ – tai padeda pritraukti daugiau klientų. Ar būtų įdomu? 🌐"

        keyboard = [
            [InlineKeyboardButton("✅ Išsaugoti kaip susisiekta", callback_data=f"save|{idx}")],
            [InlineKeyboardButton("⏭ Kitas", callback_data=f"next|{idx}")],
            [InlineKeyboardButton("🏠 Pradžia", callback_data="back")]
        ]
        await query.edit_message_text(
            f"📱 *{name}*\n📞 `{phone}`\n📍 {b['address']}\n\n✉️ *SMS tekstas (nukopijuok):*\n\n{sms}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("save|"):
        idx = int(data[5:])
        businesses = context.user_data.get("businesses", [])
        if idx < len(businesses):
            save_business(businesses[idx]["place_id"])
        await query.answer("✅ Išsaugota! Šis verslas bus praleistas ateityje.", show_alert=True)
        await show_business(query, context, idx + 1)

    elif data.startswith("next|"):
        idx = int(data[5:])
        await show_business(query, context, idx + 1)

    elif data == "back":
        keyboard = [[InlineKeyboardButton(cat, callback_data=f"cat|{cat}")] for cat in CATEGORIES]
        await query.edit_message_text(
            "🤖 *WebsiteFinder Botas*\n\n📂 Pasirink kategoriją:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def show_business(query, context, idx):
    businesses = context.user_data.get("businesses", [])
    if idx >= len(businesses):
        keyboard = [[InlineKeyboardButton("🏠 Pradžia", callback_data="back")]]
        await query.edit_message_text(
            "✅ *Visi verslai peržiūrėti!*\n\nGrįžk į pradžią ir ieškok daugiau.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    b = businesses[idx]
    keyboard = [
        [InlineKeyboardButton("📱 Gauti SMS tekstą", callback_data=f"sms|{idx}")],
        [InlineKeyboardButton("⏭ Praleisti", callback_data=f"next|{idx}")],
        [InlineKeyboardButton("🏠 Pradžia", callback_data="back")]
    ]
    await query.edit_message_text(
        f"🏪 *{b['name']}*\n📞 `{b['phone']}`\n📍 {b['address']}\n\n_{idx+1} iš {len(businesses)} verslų_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
