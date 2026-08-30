import feedparser
import os
import re
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

# ================= EXTRACT ARTICLE IMAGE =================
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
    re.IGNORECASE
)
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

def extract_og_image(url):
    """Best-effort fetch of an article's og:image. Returns None on any
    failure (timeout, blocked, no tag found) -- never raises, since a
    missing image just means falling back to a text-only post."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        match = OG_IMAGE_RE.search(resp.text)
        if match:
            return match.group(1) or match.group(2)
    except Exception:
        pass
    return None

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


def send_photo_to_telegram(photo_url, caption, chat_id=None):
    """Send one article as a photo+caption post. Telegram fetches the
    image server-side from photo_url -- no download/upload needed here.
    Returns False (never raises) so a bad image URL just triggers a
    text-only fallback rather than losing the article entirely."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram secrets not set")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id, "photo": photo_url, "caption": caption[:1024]},
            timeout=20
        )
        result = resp.json()
        if not result.get("ok"):
            print(f"⚠️ Telegram rejected photo ({photo_url}): {resp.status_code} {result}")
            return False
        print(f"✅ Telegram photo accepted message_id={result['result']['message_id']}")
        return True
    except Exception as e:
        print(f"⚠️ Telegram photo send failed with exception: {e}")
        return False

# ================= COLLECT NEWS =================
telegram_news = []       # NO LINKS -- posted to the public channel (combined digest)
personal_articles = []   # WITH LINKS + image -- one Telegram post per article
file_news = []           # WITH LINKS -- written to the local artifact file
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

        # PERSONAL CHAT (WITH LINKS + image, one post per article)
        image_url = None
        if SEND_TO_TELEGRAM and TELEGRAM_PERSONAL_CHAT_ID:
            image_url = extract_og_image(real_url)
        personal_articles.append({
            "title": title,
            "published": published,
            "link": real_url,
            "image": image_url,
        })

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

# ================= SEND PERSONAL COPY (WITH LINKS + IMAGES) =================
# Non-fatal: this is a bonus convenience feed for content creation, not
# the primary delivery. One post per article (photo+caption when an
# og:image was found, plain text otherwise) rather than a combined
# digest, since each article stands alone as potential social content.
if SEND_TO_TELEGRAM and TELEGRAM_PERSONAL_CHAT_ID:
    if personal_articles:
        for art in personal_articles:
            caption = f"{art['title']}\nPublished: {art['published']}\nLink: {art['link']}"
            sent = False
            if art["image"]:
                sent = send_photo_to_telegram(art["image"], caption, chat_id=TELEGRAM_PERSONAL_CHAT_ID)
            if not sent:
                if not send_to_telegram(caption, chat_id=TELEGRAM_PERSONAL_CHAT_ID):
                    print(f"⚠️ Personal copy failed for: {art['title']} (non-fatal)")
    else:
        send_to_telegram(
            f"திருப்பூர் மாவட்ட செய்திகள் ({DISPLAY_DATE})\n\n"
            "இன்று புதிய செய்திகள் இல்லை.",
            chat_id=TELEGRAM_PERSONAL_CHAT_ID
        )

print("✅ Script finished cleanly")
