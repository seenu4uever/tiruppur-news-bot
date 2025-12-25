import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os

print("🚀 Script started")

# ================= CONFIG =================
SEND_TO_TELEGRAM = os.getenv("SEND_TO_TELEGRAM") == "true"
DEDUP_FILE = "sent_links.txt"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ================= TIME (IST) =================
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)
timestamp = now_ist.strftime("%d-%m-%Y %I:%M %p IST")

# ================= ENSURE DEDUP FILE EXISTS =================
if not os.path.exists(DEDUP_FILE):
    open(DEDUP_FILE, "w", encoding="utf-8").close()

# ================= LOAD SENT LINKS =================
with open(DEDUP_FILE, "r", encoding="utf-8") as f:
    sent_links = set(line.strip() for line in f if line.strip())

print(f"🧠 Loaded {len(sent_links)} sent links")

# ================= WEBSITES =================
websites = [
    {
        "name": "Dinamalar",
        "url": "https://www.dinamalar.com/news/tamil-nadu-district-news-tiruppur",
        "base": "https://www.dinamalar.com",
        "tag": "p",
        "must_contain": "tiruppur",
        "limit": 10
    },
    {
        "name": "Dinamani",
        "url": "https://www.dinamani.com/all-editions/edition-coimbatore/tiruppur",
        "base": "https://www.dinamani.com",
        "tag": "h2",
        "must_contain": "/tiruppur/",
        "limit": 10
    }
]

# ================= COLLECT NEW NEWS ONLY =================
new_news = []
new_links_found = False

for site in websites:
    print(f"🔎 Fetching {site['name']}")

    try:
        r = requests.get(site["url"], headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch {site['name']}: {e}")
        continue

    soup = BeautifulSoup(r.text, "html.parser")
    count = 0

    for a in soup.find_all("a", href=True):
        if count >= site["limit"]:
            break

        tag = a.find(site["tag"])
        if not tag:
            continue

        title = tag.get_text(strip=True)
        if len(title) < 12:
            continue

        href = a["href"]
        full_url = href if href.startswith("http") else site["base"] + href

        if site["must_contain"] not in full_url.lower():
            continue

        # ===== DEDUP CHECK =====
        if full_url in sent_links:
            continue

        sent_links.add(full_url)
        new_links_found = True
        new_news.append(f"{title} - {full_url}")
        count += 1

# ================= SAVE DEDUP (ALWAYS) =================
with open(DEDUP_FILE, "w", encoding="utf-8") as f:
    for link in sorted(sent_links):
        f.write(link + "\n")

print(f"🧠 Dedup file saved with {len(sent_links)} total links")

# ================= TELEGRAM =================
def send_to_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram secrets not set")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message[:4000]
    }

    requests.post(url, data=payload)

# ================= SEND MESSAGE =================
if SEND_TO_TELEGRAM:
    if new_links_found:
        message = (
            f"Timestamp: {timestamp}\n\n"
            "📰 Tiruppur News Update\n\n" +
            "\n\n".join(new_news)
        )
        send_to_telegram(message)
        print(f"🎉 Telegram sent ({len(new_news)} new news)")
    else:
        send_to_telegram(
            f"Timestamp: {timestamp}\n\nℹ️ No new Tiruppur news found."
        )
        print("ℹ️ No new news – Telegram notification sent")

print("✅ Script finished cleanly")
