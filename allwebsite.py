import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os

print("🚀 Script started")

# ================= FLAGS =================
SEND_TO_TELEGRAM = os.getenv("SEND_TO_TELEGRAM") == "true"

# ================= TIME (IST) =================
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)
timestamp = now_ist.strftime("%d-%m-%Y %I:%M %p IST")

# ================= HEADERS =================
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ================= DEDUP FILE =================
DEDUP_FILE = "sent_links.txt"

sent_links = set()
if os.path.exists(DEDUP_FILE):
    with open(DEDUP_FILE, "r", encoding="utf-8") as f:
        sent_links = set(line.strip() for line in f if line.strip())

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

# ================= COLLECT ONLY NEW NEWS =================
new_news_lines = []
news_count = 0

for site in websites:
    try:
        r = requests.get(site["url"], headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception:
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
        new_news_lines.append(f"{title} - {full_url}")
        news_count += 1
        count += 1

# ================= SAVE DEDUP =================
if news_count > 0:
    with open(DEDUP_FILE, "w", encoding="utf-8") as f:
        for link in sorted(sent_links):
            f.write(link + "\n")

# ================= TELEGRAM =================
def send_to_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram secrets not set")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message[:4000]}
    requests.post(url, data=payload)

# ================= SEND CORRECT MESSAGE =================
if SEND_TO_TELEGRAM:
    if news_count > 0:
        message = (
            f"Timestamp: {timestamp}\n\n"
            "📰 Tiruppur News Update\n\n" +
            "\n\n".join(new_news_lines)
        )
        send_to_telegram(message)
        print(f"🎉 Telegram sent ({news_count} new news)")
    else:
        send_to_telegram(
            f"Timestamp: {timestamp}\n\nℹ️ No new Tiruppur news found."
        )
        print("ℹ️ No new news – notification sent")

print("✅ Script finished cleanly")
