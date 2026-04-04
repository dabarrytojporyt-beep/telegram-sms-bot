import logging
import json
import os
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ⚠️ ĮRAŠYK SAVO TOKEN ČIA:
TOKEN = os.environ.get("TOKEN")

SAVED_FILE = "saved.json"

# Conversation states
LAUKIA_INFO = 1

def load_saved():
    if os.path.exists(SAVED_FILE):
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_verslas(phone, data):
    saved = load_saved()
    saved[phone] = data
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)

def is_saved(phone):
    return phone in load_saved()

def parse_verslas(text):
    """Išskaito verslo info iš laisvai įvesto teksto"""
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    
    data = {
        "pavadinimas": "",
        "tipas": "",
        "adresas": "",
        "telefonas": "",
        "ivertinimas": "",
        "atsiliepimų_sk": "",
        "papildoma": ""
    }
    
    full_text = text.lower()
    
    # Ieško telefono numerio
    import re
    phone_match = re.search(r'[\+\d][\d\s\-\(\)]{7,}', text)
    if phone_match:
        data["telefonas"] = phone_match.group().strip()
    
    # Ieško įvertinimo
    rating_match = re.search(r'(\d[\.,]\d)\s*[\(\[]?(\d+)?', text)
    if rating_match:
        data["ivertinimas"] = rating_match.group(1).replace(',', '.')
        if rating_match.group(2):
            data["atsiliepimų_sk"] = rating_match.group(2)
    
    # Pirmoji eilutė = pavadinimas
    if lines:
        data["pavadinimas"] = lines[0]
    
    # Ieško adreso (g., pr., al.)
    addr_match = re.search(r'[A-ZĄČĘĖĮŠŲŪŽ][^\n]*(?:g\.|pr\.|al\.|gatvė)[^\n]*', text)
    if addr_match:
        data["adresas"] = addr_match.group().strip()
    
    # Tipas iš teksto
    tipai = {
        "kirpykl": "kirpykla", "salon": "grožio salonas", "gražio": "grožio salonas",
        "grožio": "grožio salonas", "mechani": "automechanika", "autoservis": "autoservisas",
        "restoran": "restoranas", "kavin": "kavinė", "valymo": "valymo paslaugos",
        "statybos": "statybos", "santechni": "santechnika", "elektri": "elektros darbai",
        "beauty": "grožio salonas", "hair": "plaukų salonas"
    }
    for key, val in tipai.items():
        if key in full_text:
            data["tipas"] = val
            break
    
    # Papildoma info - atsiliepimai
    reviews = re.findall(r'"([^"]{20,})"', text)
    if reviews:
        data["papildoma"] = reviews[0][:150]
    
    return data

def sukurti_sms(data):
    pav = data.get("pavadinimas", "Jūsų verslas")
    tipas = data.get("tipas", "verslas")
    ivert = data.get("ivertinimas", "")
    ats_sk = data.get("atsiliepimų_sk", "")
    
    rating_text = ""
    if ivert:
        rating_text = f" ({ivert}⭐"
        if ats_sk:
            rating_text += f", {ats_sk} atsiliepimai"
        rating_text += ")"
    
    sms = (
        f"Sveiki! Esu web dizaineris iš Klaipėdos. "
        f"Pastebėjau, kad {pav}{rating_text} neturi svetainės. "
        f"Galiu sukurti modernią, profesionalią svetainę už 50€. "
        f"Tai padėtų rasti daugiau klientų internete. Ar domintų?"
    )
    return sms

def format_verslas_info(data):
    txt = f"🏢 *{data.get('pavadinimas', '–')}*\n"
    if data.get('tipas'):
        txt += f"📌 {data['tipas']}\n"
    if data.get('adresas'):
        txt += f"📍 {data['adresas']}\n"
    if data.get('telefonas'):
        txt += f"📞 {data['telefonas']}\n"
    if data.get('ivertinimas'):
        txt += f"⭐ {data['ivertinimas']}"
        if data.get('atsiliepimų_sk'):
            txt += f" ({data['atsiliepimų_sk']} atsiliepimai)"
        txt += "\n"
    return txt

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saved = load_saved()
    keyboard = [
        [InlineKeyboardButton("➕ Įvesti naują verslą", callback_data="naujas")],
        [InlineKeyboardButton(f"📋 Išsaugoti ({len(saved)})", callback_data="saved")],
    ]
    await update.message.reply_text(
        "👋 *Website pardavimo botas*\n\n"
        "Įvesk verslo info iš Google Maps ir aš:\n"
        "• Suformuosiu SMS tekstą\n"
        "• Atidarysi SMS telefone\n"
        "• Tik paspaudžiai Siųsti ✅\n\n"
        "Spausk žemiau:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "naujas":
        await query.edit_message_text(
            "📋 *Įvesk verslo informaciją*\n\n"
            "Tiesiog nukopijuok viską iš Google Maps ir įkisk čia:\n"
            "– Pavadinimas\n"
            "– Adresas\n"
            "– Telefonas\n"
            "– Įvertinimas\n"
            "– Atsiliepimai\n\n"
            "Galima įklijuoti viską kaip yra – aš pats išrinksiiu kas reikia! 👇",
            parse_mode="Markdown"
        )
        return LAUKIA_INFO

    elif data == "saved":
        saved = load_saved()
        if not saved:
            keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="atgal_start")]]
            await query.edit_message_text(
                "📋 Nėra išsaugotų verslų.\n\nIšsaugok verslus kad nesiųstum du kartus!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        txt = "📋 *Jau kontaktuoti verslai:*\n\n"
        for phone, b in saved.items():
            txt += f"✅ *{b.get('pavadinimas','?')}* – `{phone}`\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="atgal_start")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "atgal_start":
        saved = load_saved()
        keyboard = [
            [InlineKeyboardButton("➕ Įvesti naują verslą", callback_data="naujas")],
            [InlineKeyboardButton(f"📋 Išsaugoti ({len(saved)})", callback_data="saved")],
        ]
        await query.edit_message_text(
            "👋 *Website pardavimo botas*\n\nSpausk žemiau:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("siusti_"):
        phone_enc = data.replace("siusti_", "")
        verslas = context.user_data.get("verslas", {})
        sms_text = context.user_data.get("sms_text", "")
        phone = verslas.get("telefonas", "")
        
        phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if phone_clean.startswith("0"):
            phone_clean = "+370" + phone_clean[1:]
        
        sms_link = f"sms:{phone_clean}?body={urllib.parse.quote(sms_text)}"
        
        keyboard = [
            [InlineKeyboardButton("📱 ATIDARYTI SMS →", url=sms_link)],
            [InlineKeyboardButton("✅ Išsaugoti (jau siunčiau)", callback_data="issaugoti")],
            [InlineKeyboardButton("🔙 Pradžia", callback_data="atgal_start")],
        ]
        await query.edit_message_text(
            f"{format_verslas_info(verslas)}\n"
            f"📝 *SMS tekstas:*\n_{sms_text}_\n\n"
            f"👇 Spausk mygtuką – atsidaro SMS su tekstu:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "issaugoti":
        verslas = context.user_data.get("verslas", {})
        phone = verslas.get("telefonas", "nežinomas")
        save_verslas(phone, verslas)
        
        saved = load_saved()
        keyboard = [
            [InlineKeyboardButton("➕ Kitas verslas", callback_data="naujas")],
            [InlineKeyboardButton(f"📋 Išsaugoti ({len(saved)})", callback_data="saved")],
        ]
        await query.edit_message_text(
            f"✅ *Išsaugota!*\n\n"
            f"_{verslas.get('pavadinimas', '')}_ pridėta į sąrašą.\n"
            f"Daugiau šiam verslui SMS nesiųsi.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "redaguoti_sms":
        await query.edit_message_text(
            "✏️ Įvesk naują SMS tekstą:\n\n"
            "(Arba /cancel kad atšauktum)",
            parse_mode="Markdown"
        )
        return LAUKIA_INFO

async def gauti_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    await update.message.reply_text("🔍 Analizuoju verslo informaciją...")
    
    verslas = parse_verslas(text)
    sms_text = sukurti_sms(verslas)
    
    context.user_data["verslas"] = verslas
    context.user_data["sms_text"] = sms_text
    
    phone = verslas.get("telefonas", "")
    already_saved = is_saved(phone) if phone else False
    
    warning = ""
    if already_saved:
        warning = "⚠️ *Šiam verslui jau siuntei SMS anksčiau!*\n\n"
    if not phone:
        warning += "⚠️ *Nerasta telefono numerio – pridėk rankiniu būdu*\n\n"
    
    phone_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone_clean.startswith("0"):
        phone_clean = "+370" + phone_clean[1:]
    
    sms_link = f"sms:{phone_clean}?body={urllib.parse.quote(sms_text)}" if phone_clean else "#"
    
    keyboard = [
        [InlineKeyboardButton("📱 ATIDARYTI SMS →", url=sms_link)],
        [InlineKeyboardButton("✅ Išsaugoti (jau siunčiau)", callback_data="issaugoti")],
        [InlineKeyboardButton("➕ Kitas verslas", callback_data="naujas")],
        [InlineKeyboardButton("🔙 Pradžia", callback_data="atgal_start")],
    ]
    
    await update.message.reply_text(
        f"{warning}"
        f"{format_verslas_info(verslas)}\n"
        f"📝 *SMS tekstas:*\n_{sms_text}_\n\n"
        f"👇 Spausk – atsidaro SMS su tekstu telefone:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Atšaukta. /start pradėti iš naujo.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^naujas$")],
        states={LAUKIA_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, gauti_info)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Botas paleistas! Spausk /start Telegram.")
    app.run_polling()

if __name__ == "__main__":
    main()
