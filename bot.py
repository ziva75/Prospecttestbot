import os
import logging
import requests
import csv
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "COLLE_TON_TOKEN_ICI")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "COLLE_TA_CLE_ICI")

# États de la conversation
SECTEUR, VILLE, RAYON, NOMBRE, TYPE_PROSPECT = range(5)

SECTEURS = [
    ["Restaurant", "Coiffeur", "Boulangerie"],
    ["Garage", "Plombier", "Électricien"],
    ["Médecin", "Avocat", "Comptable"],
    ["Hôtel", "Boutique", "Autre"]
]

TYPES_PROSPECT = [
    ["Sans site web", "Site obsolète", "Les deux"]
]

def check_website(url):
    """Analyse un site web et retourne un score de lacunes"""
    if not url or url == "":
        return {
            "exists": False,
            "score_lacunes": 100,
            "details": {
                "pas_de_site": True,
                "site_vieux": False,
                "pas_ssl": False,
                "pas_mobile": False,
                "lent": False,
                "pas_seo": False,
            }
        }

    details = {
        "exists": True,
        "pas_de_site": False,
        "site_vieux": False,
        "pas_ssl": False,
        "pas_mobile": False,
        "lent": False,
        "pas_seo": False,
    }

    lacunes = 0

    # Vérif SSL
    if not url.startswith("https"):
        details["pas_ssl"] = True
        lacunes += 20

    # Vérif accessibilité + headers
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        
        # Vérif contenu basique SEO
        content = resp.text.lower()
        if "<meta name=\"description\"" not in content and "<meta name='description'" not in content:
            details["pas_seo"] = True
            lacunes += 20
            
        # Vérif viewport mobile
        if "viewport" not in content:
            details["pas_mobile"] = True
            lacunes += 20

        # Vérif date copyright (site vieux)
        current_year = datetime.now().year
        old = True
        for year in range(current_year - 1, current_year + 1):
            if str(year) in content:
                old = False
                break
        if old:
            details["site_vieux"] = True
            lacunes += 20

        # Vérif vitesse (temps de réponse)
        if resp.elapsed.total_seconds() > 3:
            details["lent"] = True
            lacunes += 20

    except Exception:
        lacunes += 40

    return {
        "exists": True,
        "score_lacunes": min(lacunes, 100),
        "details": details
    }

def search_businesses(secteur, ville, rayon, nombre):
    """Recherche des entreprises via SerpAPI"""
    query = f"{secteur} {ville}"
    
    params = {
        "engine": "google_maps",
        "q": query,
        "ll": f"@{ville},15z",
        "type": "search",
        "api_key": SERPAPI_KEY,
        "num": nombre,
        "radius": rayon * 1000
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        data = response.json()
        return data.get("local_results", [])
    except Exception as e:
        logger.error(f"Erreur SerpAPI: {e}")
        return []

def format_lacunes(details):
    """Formate les lacunes en texte lisible"""
    lacunes = []
    if details.get("pas_de_site"): lacunes.append("❌ Pas de site web")
    if details.get("site_vieux"): lacunes.append("📅 Site obsolète")
    if details.get("pas_ssl"): lacunes.append("🔓 Pas de SSL (HTTP)")
    if details.get("pas_mobile"): lacunes.append("📱 Pas mobile-friendly")
    if details.get("lent"): lacunes.append("🐢 Site lent")
    if details.get("pas_seo"): lacunes.append("🔍 SEO manquant")
    return "\n".join(lacunes) if lacunes else "✅ Aucune lacune détectée"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenue sur *ProspectBot* !\n\n"
        "Je vais trouver des entreprises à démarcher pour :\n"
        "🌐 Création de site web\n"
        "📈 SEO\n"
        "📣 Google/Meta Ads\n\n"
        "Tapez /search pour lancer une recherche.",
        parse_mode="Markdown"
    )

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = SECTEURS
    await update.message.reply_text(
        "🏢 *Quel secteur d'activité ?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return SECTEUR

async def get_secteur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["secteur"] = update.message.text
    await update.message.reply_text(
        "📍 *Dans quelle ville ?*\n(ex: Paris, Lyon, Casablanca)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return VILLE

async def get_ville(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ville"] = update.message.text
    reply_keyboard = [["5 km", "10 km", "20 km", "50 km"]]
    await update.message.reply_text(
        "📏 *Quel rayon de recherche ?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return RAYON

async def get_rayon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rayon_text = update.message.text.replace(" km", "")
    context.user_data["rayon"] = int(rayon_text)
    reply_keyboard = [["10", "20", "50"]]
    await update.message.reply_text(
        "🔢 *Combien de résultats ?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return NOMBRE

async def get_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nombre"] = int(update.message.text)
    await update.message.reply_text(
        "🎯 *Quel type de prospect ?*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(TYPES_PROSPECT, one_time_keyboard=True, resize_keyboard=True)
    )
    return TYPE_PROSPECT

async def get_type_prospect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["type_prospect"] = update.message.text
    
    secteur = context.user_data["secteur"]
    ville = context.user_data["ville"]
    rayon = context.user_data["rayon"]
    nombre = context.user_data["nombre"]
    type_prospect = context.user_data["type_prospect"]

    await update.message.reply_text(
        f"🔍 Recherche en cours...\n\n"
        f"📋 Secteur: *{secteur}*\n"
        f"📍 Ville: *{ville}*\n"
        f"📏 Rayon: *{rayon} km*\n"
        f"🔢 Résultats: *{nombre}*\n"
        f"🎯 Type: *{type_prospect}*\n\n"
        f"⏳ Analyse des sites web en cours...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # Recherche
    businesses = search_businesses(secteur, ville, rayon, nombre)
    
    if not businesses:
        await update.message.reply_text("❌ Aucun résultat trouvé. Essayez une autre ville ou secteur.")
        return ConversationHandler.END

    # Analyse et filtrage
    prospects = []
    for biz in businesses:
        website = biz.get("website", "")
        analysis = check_website(website)
        score = analysis["score_lacunes"]
        
        # Filtrage selon type prospect
        if type_prospect == "Sans site web" and website:
            continue
        elif type_prospect == "Site obsolète" and not website:
            continue

        prospect = {
            "Entreprise": biz.get("title", ""),
            "Téléphone": biz.get("phone", "N/A"),
            "Adresse": biz.get("address", "N/A"),
            "Site Web": website or "❌ Aucun",
            "Note Google": biz.get("rating", "N/A"),
            "Nb Avis": biz.get("reviews", "N/A"),
            "Score Lacunes %": score,
            "Détail Lacunes": format_lacunes(analysis["details"]).replace("\n", " | "),
            "Priorité": "🔥 HAUTE" if score >= 60 else "🟡 MOYENNE" if score >= 30 else "🟢 FAIBLE"
        }
        prospects.append(prospect)

    # Tri par score décroissant
    prospects.sort(key=lambda x: x["Score Lacunes %"], reverse=True)

    if not prospects:
        await update.message.reply_text("⚠️ Aucun prospect correspondant trouvé avec ces critères.")
        return ConversationHandler.END

    # Résumé texte
    summary = f"✅ *{len(prospects)} prospects trouvés !*\n\n"
    for i, p in enumerate(prospects[:5], 1):
        summary += (
            f"*{i}. {p['Entreprise']}*\n"
            f"📞 {p['Téléphone']}\n"
            f"🌐 {p['Site Web']}\n"
            f"⚠️ Lacunes: *{p['Score Lacunes %']}%* {p['Priorité']}\n"
            f"📋 {p['Détail Lacunes']}\n\n"
        )
    
    if len(prospects) > 5:
        summary += f"_...et {len(prospects) - 5} autres dans le fichier CSV_"

    await update.message.reply_text(summary, parse_mode="Markdown")

    # Génération CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=prospects[0].keys())
    writer.writeheader()
    writer.writerows(prospects)
    
    csv_bytes = output.getvalue().encode("utf-8-sig")
    bio = io.BytesIO(csv_bytes)
    bio.name = f"prospects_{secteur}_{ville}.csv"
    
    await update.message.reply_document(
        document=bio,
        filename=bio.name,
        caption=f"📊 Liste complète de {len(prospects)} prospects — prêt pour la prospection !"
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Recherche annulée.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search_start)],
        states={
            SECTEUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_secteur)],
            VILLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ville)],
            RAYON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rayon)],
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nombre)],
            TYPE_PROSPECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_type_prospect)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    logger.info("Bot démarré !")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
