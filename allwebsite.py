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

# ================= TIME (IST) =================
now = datetime.now()
MAX_AGE = now - timedelta(days=1)
DISPLAY_DATE = now.strftime("%d %b %Y")
TIMESTAMP = now.strftime("%d-%m-%Y %I:%M %p IST")

# ================= OUTPUT FILE (WITH LINKS) =================
OUTPUT_DIR = "news_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_FILE_WITH_LINKS = os.path.join(
    OUTPUT_DIR,
    f"tiruppur_news_{now.strftime('%d-%m-%Y')}_WITH_LINKS.txt"
)

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
    return dt.strftime("%d %b %Y, %I:%M %p IST")

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
            real = qs.get("url")
            if real:
                return real[0]
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

    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message[:4000]}
    )

# ================= COLLECT NEWS =================
telegram_news = []   # NO LINKS
file_news = []       # WITH LINKS
new_links = set()
counter = 1

sources = [
    ("திருப்பூர்", "ta"),
    ("Tirupur", "en")
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

        title = entry.title.strip()
        published = format_time(ist_dt)

        # TELEGRAM (NO LINKS)
        telegram_news.append(
            f"{counter}. {title}\n"
            f"   Published: {published}"
        )

        # FILE (WITH LINKS)
        file_news.append(
            f"{counter}. {title}\n"
            f"   Published: {published}\n"
            f"   Link: {real_url}\n"
        )

        new_links.add(real_url)
        counter += 1

# ================= SAVE DEDUP =================
if new_links:
    with open(DEDUP_FILE, "a", encoding="utf-8", newline="\n") as f:
        for link in sorted(new_links):
            f.write(link + "\n")

print(f"🧠 Dedup updated (+{len(new_links)} links)")

# ================= WRITE WITH LINKS FILE =================
if file_news:
    with open(OUTPUT_FILE_WITH_LINKS, "w", encoding="utf-8") as f:
        f.write(
            "திருப்பூர் மாவட்ட செய்திகள் மற்றும் முக்கிய தகவல்களை பெற\n"
            "நம்ம திருப்பூர் வலைதளத்தை பின் தொடரவும்\n"
            "Media & News Company Tirupur\n"
            "Website : www.nammatirupur.in\n\n"
            f"திருப்பூர் மாவட்ட முக்கிய செய்திகள் ({DISPLAY_DATE})\n"
            + "=" * 70 + "\n\n"
        )
        f.write("\n".join(file_news))

    print(f"📝 WITH-LINKS file created: {OUTPUT_FILE_WITH_LINKS}")

# ================= SEND TELEGRAM =================
if SEND_TO_TELEGRAM:
    if telegram_news:
        message = (
            "திருப்பூர் மாவட்ட செய்திகள் மற்றும் முக்கிய தகவல்களை பெற\n"
            "நம்ம திருப்பூர் வலைதளத்தை பின் தொடரவும்\n"
            "Media & News Company Tirupur\n"
            "Website : www.nammatirupur.in\n\n"
            f"திருப்பூர் மாவட்ட முக்கிய செய்திகள் ({DISPLAY_DATE})\n"
            + "=" * 70 + "\n\n"
            + "\n\n".join(telegram_news)
        )
        send_to_telegram(message)
        print("📨 Telegram sent (NO LINKS)")
    else:
        send_to_telegram(
            f"திருப்பூர் மாவட்ட செய்திகள் ({DISPLAY_DATE})\n\n"
            "இன்று புதிய செய்திகள் இல்லை."
        )

print("✅ Script finished cleanly")
