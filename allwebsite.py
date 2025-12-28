import feedparser
import os
import email.utils
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

print("🚀 Script started")

# ================= CONFIG =================
SEND_TO_TELEGRAM = os.getenv("SEND_TO_TELEGRAM") == "true"
DEDUP_FILE = "sent_links.txt"

# ================= TIME (IST – SAFE) =================
now = datetime.now()
timestamp = now.strftime("%d-%m-%Y %I:%M %p IST")
MAX_AGE = now - timedelta(days=1)

# ================= ENSURE DEDUP FILE EXISTS =================
if not os.path.exists(DEDUP_FILE):
    open(DEDUP_FILE, "w", encoding="utf-8").close()

# ================= LOAD SENT LINKS =================
with open(DEDUP_FILE, "r", encoding="utf-8") as f:
    sent_links = set(line.strip() for line in f if line.strip())

print(f"🧠 Loaded {len(sent_links)} sent links")

# ================= TIME CONVERSION =================
def gmt_to_ist(published_str):
    try:
        dt = email.utils.parsedate_to_datetime(published_str)
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt + timedelta(hours=5, minutes=30)
    except Exception:
        return None

def format_time(dt):
    if not dt:
        return "Time not available"
    return dt.strftime("%d-%m-%Y %I:%M %p IST")

# ================= GOOGLE NEWS =================
def google_news(query, lang):
    if lang == "ta":
        url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=ta-IN&gl=IN&ceid=IN:ta"
    else:
        url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=en-IN&gl=IN&ceid=IN:en"

    return feedparser.parse(url).entries

# ================= RESOLVE GOOGLE LINK =================
def resolve_google_url(url):
    try:
        parsed = urlparse(url)
        if "news.google.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            return qs.get("url", [url])[0]
        return url
    except Exception:
        return url

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

# ================= COLLECT NEWS =================
new_news = []
new_links = set()

sources = [
    ("Tirupur", "en"),
    ("திருப்பூர்", "ta")
]

for query, lang in sources:
    print(f"🔎 Fetching Google News: {query}")

    for entry in google_news(query, lang):
        real_url = resolve_google_url(entry.link)

        if real_url in sent_links or real_url in new_links:
            continue

        ist_dt = gmt_to_ist(entry.get("published", ""))
        if ist_dt and ist_dt < MAX_AGE:
            continue

        title = entry.title
        time_str = format_time(ist_dt)

        new_news.append(f"• {title}\n{real_url}")
        new_links.add(real_url)

# ================= SAVE DEDUP =================
if new_links:
    with open(DEDUP_FILE, "a", encoding="utf-8", newline="\n") as f:
        for link in sorted(new_links):
            f.write(link + "\n")

print(f"🧠 Dedup updated (+{len(new_links)} links)")

# ================= SEND TELEGRAM =================
if SEND_TO_TELEGRAM:
    if new_news:
        message = (
            f"Timestamp: {timestamp}\n\n"
            "📰 Tiruppur News Update\n\n" +
            "\n\n".join(new_news)
        )
        send_to_telegram(message)
        print(f"🎉 Telegram sent ({len(new_news)} news)")
    else:
        send_to_telegram(
            f"Timestamp: {timestamp}\n\nℹ️ No new Tiruppur news found."
        )
        print("ℹ️ No new news")

print("✅ Script finished cleanly")
