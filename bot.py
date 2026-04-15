import os
import logging
import requests
import csv
import io
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

# Sessions utilisateurs
user_sessions = {}

def send_message(chat_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if keyboard:
        payload["reply_markup"] = {
            "keyboard": keyboard,
            "one_time_keyboard": True,
            "resize_keyboard": True
        }
    else:
        payload["reply_markup"] = {"remove_keyboard": True}
    requests.post(url, json=payload)

def send_document(chat_id, file_bytes, filename, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    requests.post(url, data={"chat_id": chat_id, "caption": caption}, 
                  files={"document": (filename, file_bytes)})

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        return resp.json()
    except:
        return {"ok": False, "result": []}

def check_website(url):
    if not url:
        return {"exists": False, "score_lacunes": 100, "details": {
            "pas_de_site": True, "site_vieux": False,
            "pas_ssl": False, "pas_mobile": False, "lent": False, "pas_seo": False
        }}

    details = {"exists": True, "pas_de_site": False, "site_vieux": False,
                "pas_ssl": False, "pas_mobile": False, "lent": False, "pas_seo": False}
    lacunes = 0

    if not url.startswith("https"):
        details["pas_ssl"] = True
        lacunes += 20

    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        content = resp.text.lower()

        if 'meta name="description"' not in content and "meta name='description'" not in content:
            details["pas_seo"] = True
            lacunes += 20

        if "viewport" not in content:
            details["pas_mobile"] = True
            lacunes += 20

        current_year = datetime.now().year
        old = all(str(y) not in content for y in range(current_year - 1, current_year + 1))
        if old:
            details["site_vieux"] = True
            lacunes += 20

        if resp.elapsed.total_seconds() > 3:
            details["lent"] = True
            lacunes += 20
    except:
        lacunes += 40

    return {"exists": True, "score_lacunes": min(lacunes, 100), "details": details}

def format_lacunes(details):
    lacunes = []
    if details.get("pas_de_site"): lacunes.append("Pas de site web")
    if details.get("site_vieux"): lacunes.append("Site obsolete")
    if details.get("pas_ssl"): lacunes.append("Pas de SSL")
    if details.get("pas_mobile"): lacunes.append("Pas mobile-friendly")
    if details.get("lent"): lacunes.append("Site lent")
    if details.get("pas_seo"): lacunes.append("SEO manquant")
    return " | ".join(lacunes) if lacunes else "Aucune lacune"

def search_businesses(secteur, ville, nombre):
    params = {
        "engine": "google_maps",
        "q": f"{secteur} {ville}",
        "type": "search",
        "api_key": SERPAPI_KEY,
        "hl": "fr"
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        data = resp.json()
        return data.get("local_results", [])[:nombre]
    except Exception as e:
        logger.error(f"Erreur SerpAPI: {e}")
        return []

def handle_message(chat_id, text):
    session = user_sessions.get(chat_id, {})
    step = session.get("step", "start")

    if text == "/start":
        user_sessions[chat_id] = {"step": "start"}
        send_message(chat_id,
            "👋 Bienvenue sur *ProspectBot* !\n\n"
            "Je trouve des entreprises a demarcher pour :\n"
            "🌐 Creation de site web\n"
            "📈 SEO\n"
            "📣 Google/Meta Ads\n\n"
            "Tapez /search pour lancer une recherche."
        )

    elif text == "/search" or step == "start":
        user_sessions[chat_id] = {"step": "secteur"}
        send_message(chat_id, "🏢 *Quel secteur d'activite ?*", keyboard=[
            ["Restaurant", "Coiffeur", "Boulangerie"],
            ["Garage", "Plombier", "Electricien"],
            ["Medecin", "Avocat", "Boutique"]
        ])

    elif step == "secteur":
        user_sessions[chat_id] = {"step": "ville", "secteur": text}
        send_message(chat_id, "📍 *Dans quelle ville ?*\n(ex: Paris, Lyon, Casablanca)")

    elif step == "ville":
        session["ville"] = text
        session["step"] = "nombre"
        user_sessions[chat_id] = session
        send_message(chat_id, "🔢 *Combien de resultats ?*", keyboard=[
            ["10", "20", "50"]
        ])

    elif step == "nombre":
        try:
            nombre = int(text)
        except:
            nombre = 10
        session["nombre"] = nombre
        session["step"] = "type"
        user_sessions[chat_id] = session
        send_message(chat_id, "🎯 *Quel type de prospect ?*", keyboard=[
            ["Sans site web", "Site obsolete", "Les deux"]
        ])

    elif step == "type":
        session["type"] = text
        session["step"] = "done"
        user_sessions[chat_id] = session

        secteur = session["secteur"]
        ville = session["ville"]
        nombre = session["nombre"]
        type_prospect = session["type"]

        send_message(chat_id,
            f"🔍 Recherche en cours...\n\n"
            f"📋 Secteur: *{secteur}*\n"
            f"📍 Ville: *{ville}*\n"
            f"🔢 Resultats: *{nombre}*\n"
            f"🎯 Type: *{type_prospect}*\n\n"
            f"⏳ Analyse des sites web..."
        )

        businesses = search_businesses(secteur, ville, nombre)

        if not businesses:
            send_message(chat_id, "❌ Aucun resultat. Essayez une autre ville ou secteur.\n\nTapez /search pour recommencer.")
            return

        prospects = []
        for biz in businesses:
            website = biz.get("website", "")
            analysis = check_website(website)
            score = analysis["score_lacunes"]

            if type_prospect == "Sans site web" and website:
                continue
            elif type_prospect == "Site obsolete" and not website:
                continue

            prospects.append({
                "Entreprise": biz.get("title", ""),
                "Telephone": biz.get("phone", "N/A"),
                "Adresse": biz.get("address", "N/A"),
                "Site Web": website or "Aucun",
                "Note Google": biz.get("rating", "N/A"),
                "Nb Avis": biz.get("reviews", "N/A"),
                "Score Lacunes %": score,
                "Detail Lacunes": format_lacunes(analysis["details"]),
                "Priorite": "HAUTE" if score >= 60 else "MOYENNE" if score >= 30 else "FAIBLE"
            })

        prospects.sort(key=lambda x: x["Score Lacunes %"], reverse=True)

        if not prospects:
            send_message(chat_id, "⚠️ Aucun prospect avec ces criteres.\n\nTapez /search pour recommencer.")
            return

        summary = f"✅ *{len(prospects)} prospects trouves !*\n\n"
        for i, p in enumerate(prospects[:5], 1):
            summary += (
                f"*{i}. {p['Entreprise']}*\n"
                f"📞 {p['Telephone']}\n"
                f"🌐 {p['Site Web']}\n"
                f"⚠️ Lacunes: *{p['Score Lacunes %']}%* — {p['Priorite']}\n"
                f"📋 {p['Detail Lacunes']}\n\n"
            )

        if len(prospects) > 5:
            summary += f"_...et {len(prospects) - 5} autres dans le CSV_"

        send_message(chat_id, summary)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=prospects[0].keys())
        writer.writeheader()
        writer.writerows(prospects)
        csv_bytes = output.getvalue().encode("utf-8-sig")

        send_document(chat_id, csv_bytes,
            f"prospects_{secteur}_{ville}.csv",
            f"📊 {len(prospects)} prospects — pret pour la prospection !")

        send_message(chat_id, "Tapez /search pour une nouvelle recherche 🚀")
        user_sessions[chat_id] = {"step": "start"}

def main():
    logger.info("Bot demarre !")
    offset = None
    while True:
        updates = get_updates(offset)
        if not updates.get("ok"):
            continue
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            if chat_id and text:
                try:
                    handle_message(chat_id, text)
                except Exception as e:
                    logger.error(f"Erreur: {e}")

if __name__ == "__main__":
    main()
