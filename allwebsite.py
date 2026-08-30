import feedparser
import os
import email.utils
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

print("🚀 Script started")

# ================= CONFIG =================
SEND_TO_TELEGRAM = os.getenv("SEND_TO_TELEGRAM") == "true"
# Personal chat copy WITH links -- restores what used to be sent to the
# "Tiruppur news bot" 1:1 chat before the automated pipeline (Dec 2025)
# only ever wired up the no-links channel post. Optional: if unset, this
# second send is simply skipped, no error.
TELEGRAM_PERSONAL_CHAT_ID = os.getenv("TELEGRAM_PERSONAL_CHAT_ID")
DEDUP_FILE = "sent_links.txt"
DEDUP_RETENTION_DAYS = 30  # links older than this can never match a when:1d query again
TELEGRAM_MAX_LEN = 4000

# ================= TIME (IST) =================
now = datetime.now()
DISPLAY_DATE = now.strftime("%d %b %Y")

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
# Format: "YYYY-MM-DD|url" per line. A link can never be re-matched by a
# when:1d query once it's more than a day or two old, so anything past
# DEDUP_RETENTION_DAYS is pure dead weight -- pruned on every run to keep
# this file (and the repo's commit history) from growing forever.
# Lines from before this format existed (no "|") are already far older
# than the retention window by definition, so they're dropped outright.
today_date = now.date()
sent_links = set()
kept_entries = []  # (date_str, url) pairs surviving the prune

with open(DEDUP_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or "|" not in line:
            continue
        date_str, url = line.split("|", 1)
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (today_date - entry_date).days <= DEDUP_RETENTION_DAYS:
            kept_entries.append((date_str, url))
            sent_links.add(url)

print(f"🧠 Loaded {len(sent_links)} sent links (pruned to last {DEDUP_RETENTION_DAYS} days)")

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
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"❌ Failed to fetch/parse feed for '{query}': {e}")
        return []
    if feed.bozo:
        print(f"⚠️ Feed for '{query}' parsed with warnings: {feed.bozo_exception}")
    return feed.entries

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
def send_to_telegram(message, chat_id=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram secrets not set")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=15
        )
        result = resp.json()
        if not result.get("ok"):
            print(f"❌ Telegram API rejected the message: {resp.status_code} {result}")
            return False
        print(f"✅ Telegram accepted message_id={result['result']['message_id']}")
        return True
    except Exception as e:
        print(f"❌ Telegram send failed with exception: {e}")
        return False

# ================= COLLECT NEWS =================
telegram_news = []            # NO LINKS -- posted to the public channel
telegram_news_with_links = [] # WITH LINKS -- posted to the personal chat
file_news = []                 # WITH LINKS -- written to the local artifact file
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

        # ✅ ONLY TODAY'S NEWS (calendar-based)
        if ist_dt and ist_dt.date() != now.date():
            continue

        title = entry.title.strip()
        published = format_time(ist_dt)

        # TELEGRAM (NO LINKS)
        telegram_news.append(
            f"{counter}. {title}\n"
            f"   Published: {published}"
        )

        # TELEGRAM (WITH LINKS, personal chat)
        telegram_news_with_links.append(
            f"{counter}. {title}\n"
            f"   Published: {published}\n"
            f"   Link: {real_url}"
        )

        # FILE (WITH LINKS)
        file_news.append(
            f"{counter}. {title}\n"
            f"   Published: {published}\n"
            f"   Link: {real_url}\n"
        )

        new_links.add(real_url)
        counter += 1

# ================= SAVE DEDUP (rewrite, pruned) =================
today_str = now.strftime("%Y-%m-%d")
for link in sorted(new_links):
    kept_entries.append((today_str, link))

with open(DEDUP_FILE, "w", encoding="utf-8", newline="\n") as f:
    for date_str, url in kept_entries:
        f.write(f"{date_str}|{url}\n")

print(f"🧠 Dedup updated (+{len(new_links)} links, {len(kept_entries)} total after pruning)")

# ================= WRITE WITH LINKS FILE =================
if file_news:
    with open(OUTPUT_FILE_WITH_LINKS, "w", encoding="utf-8") as f:
        f.write(
            "திருப்பூர் மாவட்ட செய்திகள் மற்றும் முக்கிய தகவல்களை பெற\n"
            "நம்ம திருப்பூர் வலைதளத்தை பின் தொடரவும்\n"
            "Media & News Company Tirupur\n"
            "Website : www.nammatirupur.in\n\n"
            f"திருப்பூர் மாவட்ட மற்றும் முக்கிய செய்திகள் ({DISPLAY_DATE})\n"
            + "=" * 70 + "\n\n"
        )
        f.write("\n".join(file_news))

    print(f"📝 WITH-LINKS file created: {OUTPUT_FILE_WITH_LINKS}")

HEADER = (
    "திருப்பூர் மாவட்ட செய்திகள் மற்றும் முக்கிய தகவல்களை பெற\n"
    "நம்ம திருப்பூர் வலைதளத்தை பின் தொடரவும்\n"
    "Media & News Company Tirupur\n"
    "Website : www.nammatirupur.in\n\n"
    f"திருப்பூர் மாவட்ட மற்றும் முக்கிய செய்திகள் ({DISPLAY_DATE})\n"
    + "=" * 70 + "\n\n"
)


def chunk_items(header, items, max_len):
    """Group items into message chunks that each stay under max_len,
    repeating the header on every chunk so each message stands alone."""
    chunks = []
    current = []
    current_len = len(header)
    for item in items:
        item_len = len(item) + 2  # +2 for the "\n\n" join separator
        if current and current_len + item_len > max_len:
            chunks.append(header + "\n\n".join(current))
            current = []
            current_len = len(header)
        current.append(item)
        current_len += item_len
    if current:
        chunks.append(header + "\n\n".join(current))
    return chunks


# ================= SEND TELEGRAM =================
telegram_ok = True
if SEND_TO_TELEGRAM:
    if telegram_news:
        messages = chunk_items(HEADER, telegram_news, TELEGRAM_MAX_LEN)
        for i, msg in enumerate(messages, 1):
            if len(messages) > 1:
                msg += f"\n\n(part {i}/{len(messages)})"
            if not send_to_telegram(msg):
                telegram_ok = False
    else:
        telegram_ok = send_to_telegram(
            f"திருப்பூர் மாவட்ட செய்திகள் ({DISPLAY_DATE})\n\n"
            "இன்று புதிய செய்திகள் இல்லை."
        )

if not telegram_ok:
    print("❌ Script finished with Telegram send failure")
    raise SystemExit(1)

# ================= SEND PERSONAL COPY (WITH LINKS) =================
# Non-fatal: this is a bonus convenience copy, not the primary delivery.
# A failure here (e.g. you haven't messaged the bot recently) shouldn't
# fail the whole run.
if SEND_TO_TELEGRAM and TELEGRAM_PERSONAL_CHAT_ID:
    if telegram_news_with_links:
        personal_messages = chunk_items(HEADER, telegram_news_with_links, TELEGRAM_MAX_LEN)
        for i, msg in enumerate(personal_messages, 1):
            if len(personal_messages) > 1:
                msg += f"\n\n(part {i}/{len(personal_messages)})"
            if not send_to_telegram(msg, chat_id=TELEGRAM_PERSONAL_CHAT_ID):
                print("⚠️ Personal with-links copy failed to send (non-fatal)")
    else:
        send_to_telegram(
            f"திருப்பூர் மாவட்ட செய்திகள் ({DISPLAY_DATE})\n\n"
            "இன்று புதிய செய்திகள் இல்லை.",
            chat_id=TELEGRAM_PERSONAL_CHAT_ID
        )

print("✅ Script finished cleanly")
