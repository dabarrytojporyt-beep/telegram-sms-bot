import logging
import json
import os
import re
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("TOKEN")
SAVED_FILE = "saved.json"
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
    data = {"pavadinimas": "", "telefonas": "", "ivertinimas": "", "atsiliepimų_sk": "", "adresas": ""}
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

    phone_match = re.search(r'[\(]?0[\-\s]?\d{3}[\s\-]?\d{5}', text)
    if phone_match:
        data["telefonas"] = phone_match.group().strip()

    rating_match = re.search(r'(\d[\.,]\d)\s*\(?(\d+)?\)?', text)
    if rating_match:
        data["ivertinimas"] = rating_match.group(1).replace(',', '.')
        if rating_match.group(2):
            data["atsiliepimų_sk"] = rating_match.group(2)

    for line in lines:
        if len(line) > 4 and not re.match(r'^[\d\.\(\)\+\-\s]+$', line) and not re.match(r'^(Overview|Reviews|About|Directions|Save|Nearby|Share|Book)', line):
            data["pavadinimas"] = line
            break

    addr = re.search(r'[A-ZĄČĘĖĮŠŲŪŽ][^\n]*(?:g\.|pr\.|al\.|gatvė)[^\n]*', text)
    if addr:
        data["adresas"] = addr.group().strip()

    return data

def sukurti_sms(data):
    pav = data.get("pavadinimas", "Jūsų verslas")
    ivert = data.get("ivertinimas", "")
    ats_sk = data.get("atsiliepimų_sk", "")
    rating_text = ""
    if ivert:
        rating_text = f" ({ivert}⭐"
        if ats_sk:
            rating_text += f", {ats_sk} atsiliepimai"
        rating_text += ")"
    return (
        f"Sveiki! Esu web dizaineris is Klaipedos. "
        f"Pastebejau, kad {pav}{rating_text} neturi svetaines. "
        f"Galiu sukurti moderni svetaine uz 50EUR - tai padetu rasti daugiau klientu. Ar domintu?"
    )

def format_info(data):
    txt = f"🏢 *{data.get('pavadinimas', '–')}*\n"
    if data.get('adresas'):
        txt += f"📍 {data['adresas']}\n"
    if data.get('telefonas'):
        txt += f"📞 `{data['telefonas']}`\n"
    if data.get('ivertinimas'):
        txt += f"⭐ {data['ivertinimas']}"
        if data.get('atsiliepimų_sk'):
            txt += f" ({data['atsiliepimų_sk']} atsiliepimų)"
        txt += "\n"
    return txt

def gauti_sms_link(phone, sms_text):
    p = re.sub(r'[\s\-\(\)]', '', phone)
    p = p.replace('0-', '')
    if p.startswith('0'):
        p = '+370' + p[1:]
    if not p.startswith('+'):
        p = '+370' + p
    return f"sms:{p}?body={urllib.parse.quote(sms_text)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saved = load_saved()
    kb = [
        [InlineKeyboardButton("➕ Ivesti nauja versla", callback_data="naujas")],
        [InlineKeyboardButton(f"📋 Jau siusti ({len(saved)})", callback_data="saved")],
    ]
    await update.message.reply_text(
        "👋 *SMS pardavimo botas*\n\n"
        "Kaip veikia:\n"
        "1. Spaudzi *Ivesti nauja versla*\n"
        "2. Nukopijuoji info is Google Maps ir ikeli\n"
        "3. Spaudzi *ATIDARYTI SMS*\n"
        "4. Telefone tik spaudzi *Siusti*",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "naujas":
        await query.edit_message_text(
            "📋 *Iveski verslo informacija*\n\n"
            "Nukopijuok viska is Google Maps ir ikisk cia.\n"
            "As pats isrinksiu kas reikia! 👇",
            parse_mode="Markdown"
        )
        return LAUKIA_INFO

    elif data == "saved":
        saved = load_saved()
        if not saved:
            kb = [[InlineKeyboardButton("🔙 Atgal", callback_data="atgal")]]
            await query.edit_message_text("📋 Nera issaugotu verslu.", reply_markup=InlineKeyboardMarkup(kb))
            return
        txt = "📋 *Jau siusti verslai:*\n\n"
        for phone, b in saved.items():
            txt += f"✅ *{b.get('pavadinimas','?')}* – `{phone}`\n"
        kb = [[InlineKeyboardButton("🔙 Atgal", callback_data="atgal")]]
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "atgal":
        saved = load_saved()
        kb = [
            [InlineKeyboardButton("➕ Ivesti nauja versla", callback_data="naujas")],
            [InlineKeyboardButton(f"📋 Jau siusti ({len(saved)})", callback_data="saved")],
        ]
        await query.edit_message_text(
            "👋 *SMS pardavimo botas*\n\nSpausk zemiau:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

    elif data == "issaugoti":
        verslas = context.user_data.get("verslas", {})
        phone = verslas.get("telefonas", "nezinomas")
        save_verslas(phone, verslas)
        saved = load_saved()
        kb = [
            [InlineKeyboardButton("➕ Kitas verslas", callback_data="naujas")],
            [InlineKeyboardButton(f"📋 Jau siusti ({len(saved)})", callback_data="saved")],
        ]
        await query.edit_message_text(
            f"✅ *Issaugota!*\n_{verslas.get('pavadinimas','')}_ prideta i sarasa.\n\nKita versla?",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

async def gauti_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    verslas = parse_verslas(text)
    sms_text = sukurti_sms(verslas)
    context.user_data["verslas"] = verslas
    context.user_data["sms_text"] = sms_text

    phone = verslas.get("telefonas", "")
    saved_warning = "DĖMESIO: Šiam numeriui jau siuntei!\n\n" if phone and is_saved(phone) else ""
    no_phone = "DĖMESIO: Nerasta telefono - iveski ranka\n\n" if not phone else ""

    sms_link = gauti_sms_link(phone, sms_text) if phone else "sms:"

    kb = [
        [InlineKeyboardButton("📱 ATIDARYTI SMS", url=sms_link)],
        [InlineKeyboardButton("✅ Issaugoti (issiunčiau)", callback_data="issaugoti")],
        [InlineKeyboardButton("➕ Kitas verslas", callback_data="naujas")],
    ]

    await update.message.reply_text(
        f"{saved_warning}{no_phone}"
        f"{format_info(verslas)}\n"
        f"📝 *SMS tekstas:*\n_{sms_text}_\n\n"
        f"👇 Spausk telefone:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Atsaukta. /start pradeti is naujo.")
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
    print("Botas paleistas!")
    app.run_polling()

if __name__ == "__main__":
    main()
