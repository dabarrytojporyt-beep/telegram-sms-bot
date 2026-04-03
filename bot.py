import os
import json
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TOKEN")
MAPS_API = os.environ.get("MAPS_API")

SAVED_FILE = "saved_businesses.json"

CATEGORIES = {
    "kirpyklos": "hair salon",
    "automechanikai": "auto repair",
    "restoranai": "restaurant",
    "kavinės": "cafe",
    "santechnikai": "plumber",
    "grožio_salonai": "beauty salon",
    "sporto_klubai": "gym",
    "vaistinės": "pharmacy"
}

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

def search_businesses(category_en, city="Klaipėda"):
    saved = load_saved()
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"{category_en} in {city}",
        "key": MAPS_API,
        "language": "lt"
    }
    response = requests.get(url, params=params)
    data = response.json()
    
    results = []
    for place in data.get("results", []):
        place_id = place.get("place_id")
        if place_id in saved:
            continue
        website = place.get("website", "")
        if website:
            continue
        
        # Get details for phone
        detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
        detail_params = {
            "place_id": place_id,
            "fields": "name,formatted_phone_number,formatted_address,website",
            "key": MAPS_API
        }
        detail_resp = requests.get(detail_url, params=detail_params)
        detail = detail_resp.json().get("result", {})
        
        phone = detail.get("formatted_phone_number", "")
        if not phone:
            continue
        if detail.get("website"):
            continue
            
        results.append({
            "place_id": place_id,
            "name": place.get("name"),
            "phone": phone,
            "address": detail.get("formatted_address", "")
        })
        
        if len(results) >= 10:
            break
    
    return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for lt_name in CATEGORIES.keys():
        keyboard.append([InlineKeyboardButton(lt_name.capitalize(), callback_data=f"cat_{lt_name}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔍 Pasirink verslo kategoriją kurią nori ieškoti:",
        reply_markup=reply_markup
    )

async def show_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saved = load_saved()
    if not saved:
        await update.message.reply_text("📋 Dar nėra išsaugotų verslų.")
        return
    await update.message.reply_text(f"📋 Išsaugota verslų: {len(saved)}\n(Šie verslai bus praleisti ieškant)")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("cat_"):
        cat_lt = data[4:]
        cat_en = CATEGORIES.get(cat_lt, cat_lt)
        await query.edit_message_text(f"🔍 Ieškau {cat_lt} be svetainės... Palaukite!")
        
        businesses = search_businesses(cat_en)
        
        if not businesses:
            await query.edit_message_text("😕 Nerasta verslų be svetainės šioje kategorijoje. Bandyk kitą!")
            return
        
        context.user_data["businesses"] = businesses
        context.user_data["current_index"] = 0
        
        await show_business(query, context, 0)
    
    elif data.startswith("sms_"):
        idx = int(data[4:])
        businesses = context.user_data.get("businesses", [])
        if idx < len(businesses):
            b = businesses[idx]
            phone = b["phone"].replace(" ", "").replace("-", "").replace("+370", "0")
            name = b["name"]
            sms_text = f"Sveiki! Pastebėjau kad {name} neturi svetainės. Kuriu profesionalias svetaines verslams už 50€. Tai padeda pritraukti daugiau klientų internete. Ar būtų įdomu? 🌐"
            
            sms_link = f"sms:{phone}?body={requests.utils.quote(sms_text)}"
            
            keyboard = [
                [InlineKeyboardButton("✅ Išsaugoti (jau susisiekta)", callback_data=f"save_{idx}")],
                [InlineKeyboardButton("⏭ Kitas verslas", callback_data=f"next_{idx}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📱 *{name}*\n📞 {b['phone']}\n📍 {b['address']}\n\n"
                f"Tekstas žinutei:\n_{sms_text}_\n\n"
                f"👆 Nukopijuok tekstą ir numerį ir siųsk SMS!",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    
    elif data.startswith("save_"):
        idx = int(data[5:])
        businesses = context.user_data.get("businesses", [])
        if idx < len(businesses):
            save_business(businesses[idx]["place_id"])
            await query.answer("✅ Išsaugota!", show_alert=True)
            await show_business(query, context, idx + 1)
    
    elif data.startswith("next_"):
        idx = int(data[5:])
        await show_business(query, context, idx + 1)
    
    elif data == "back_menu":
        keyboard = []
        for lt_name in CATEGORIES.keys():
            keyboard.append([InlineKeyboardButton(lt_name.capitalize(), callback_data=f"cat_{lt_name}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🔍 Pasirink verslo kategoriją:", reply_markup=reply_markup)

async def show_business(query, context, idx):
    businesses = context.user_data.get("businesses", [])
    
    if idx >= len(businesses):
        await query.edit_message_text("✅ Visi verslai peržiūrėti! Pradėk iš naujo su /start")
        return
    
    b = businesses[idx]
    keyboard = [
        [InlineKeyboardButton("📱 Parašyti SMS", callback_data=f"sms_{idx}")],
        [InlineKeyboardButton("⏭ Praleisti", callback_data=f"next_{idx}")],
        [InlineKeyboardButton("🔙 Meniu", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🏪 *{b['name']}*\n📞 {b['phone']}\n📍 {b['address']}\n\n_{idx+1} iš {len(businesses)}_",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saved", show_saved))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
