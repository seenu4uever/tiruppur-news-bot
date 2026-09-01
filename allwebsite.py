import html
import os
import re
import requests
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

print("🚀 Script started")

# ================= CONFIG =================
SEND_TO_TELEGRAM = os.getenv("SEND_TO_TELEGRAM") == "true"
# Personal chat copy WITH links -- restores what used to be sent to the
# "Tiruppur news bot" 1:1 chat before the automated pipeline (Dec 2025)
# only ever wired up the no-links channel post. Optional: if unset, this
# second send is simply skipped, no error.
TELEGRAM_PERSONAL_CHAT_ID = os.getenv("TELEGRAM_PERSONAL_CHAT_ID")
DEDUP_FILE = "sent_links.txt"
DEDUP_RETENTION_DAYS = 30
TELEGRAM_MAX_LEN = 4000

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ================= TIME (IST) =================
now = datetime.now()
DISPLAY_DATE = now.strftime("%d %b %Y")

# ================= OUTPUT FILE (WITH LINKS) =================
OUTPUT_DIR = "news_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE_WITH_LINKS = os.path.join(
    OUTPUT_DIR, f"tiruppur_news_{now.strftime('%d-%m-%Y')}_WITH_LINKS.txt"
)

# ================= ENSURE DEDUP FILE EXISTS =================
if not os.path.exists(DEDUP_FILE):
    open(DEDUP_FILE, "w", encoding="utf-8").close()

# ================= LOAD SENT LINKS =================
# Format: "YYYY-MM-DD|url" per line, pruned to the last DEDUP_RETENTION_DAYS
# on every run to keep this file (and the repo's commit history) bounded.
today_date = now.date()
sent_links = set()
kept_entries = []

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

# ================= NEWS SOURCES =================
# Direct site scraping, not Google News -- Google's RSS links mostly can't
# be resolved to the real publisher page without executing JS, so any
# "summary" fetched from them was Google's own generic boilerplate, not
# real per-article content (found 2026-08-31). These 3 sites' own listing
# and article pages are the real thing, so their og:description/og:image
# are genuinely per-article. Dailythanthi's old district-page URL now
# redirects to its generic homepage -- dropped until a working URL is found.
SITES = [
    {
        "name": "Dinamalar",
        "url": "https://www.dinamalar.com/news/tamil-nadu-district-news-tiruppur",
        "must_contain": "district-news-tiruppur/",
    },
    {
        "name": "Dinakaran",
        "url": "https://www.dinakaran.com/district/tiruppur",
        "must_contain": "tiruppur",
        "exclude_exact": "https://www.dinakaran.com/district/tiruppur",
    },
    {
        "name": "Dinamani",
        "url": "https://www.dinamani.com/all-editions/edition-coimbatore/tiruppur",
        "must_contain": "/tiruppur/",
        "require_substr": "/20",  # article URLs embed a year, category nav links don't
    },
]

TITLE_PREFIX_DUPE_RE = re.compile(r'^(திருப்பூர்)(?=[஀-௿])')


def clean_title(title):
    """Some listing pages concatenate the category label directly onto
    the headline with no separator (e.g. 'திருப்பூர்பல்லடம்...') -- strip
    that duplicate leading category word when glued straight onto Tamil
    text with no space."""
    return TITLE_PREFIX_DUPE_RE.sub('', html.unescape(title)).strip()


def scrape_site(site):
    """Fetch a site's Tirupur listing page and return [(title, url), ...],
    deduped by URL (keeping the longest title seen, since some pages have
    both a thumbnail link and a text link pointing at the same article)."""
    try:
        resp = requests.get(site["url"], headers=BROWSER_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch {site['name']}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    best = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(site["url"], a["href"])
        if site["must_contain"] not in href:
            continue
        if site.get("require_substr") and site["require_substr"] not in href:
            continue
        if site.get("exclude_exact") and href.rstrip("/") == site["exclude_exact"].rstrip("/"):
            continue
        title = clean_title(a.get_text(strip=True))
        if not title or len(title) < 5:
            continue
        if href not in best or len(title) > len(best[href]):
            best[href] = title
    # best is {href: title} -- .items() yields (href, title), so flip to
    # match this function's documented (title, url) contract every caller relies on.
    return [(title, href) for href, title in best.items()]


# ================= EXTRACT ARTICLE IMAGE + DESCRIPTION =================
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
    re.IGNORECASE
)
OG_DESC_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:description["\']',
    re.IGNORECASE
)
DESC_FALLBACK_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    re.IGNORECASE
)
TRAILING_HASHTAGS_RE = re.compile(r'(\s*#\S+)+\s*$')


def _unescape_html(text):
    return (text.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
                .replace("&lt;", "<").replace("&gt;", ">"))


def _clean_description(text):
    return TRAILING_HASHTAGS_RE.sub('', text).strip()


def fetch_article_meta(url):
    """Best-effort single fetch of a real article's og:image and
    description. Returns (image_url_or_None, description_or_None) --
    never raises, since a missing field just means falling back to
    title-only."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        html = resp.text
        img_match = OG_IMAGE_RE.search(html)
        image = (img_match.group(1) or img_match.group(2)) if img_match else None

        desc_match = OG_DESC_RE.search(html) or DESC_FALLBACK_RE.search(html)
        description = None
        if desc_match:
            description = _clean_description(_unescape_html(desc_match.group(1) or desc_match.group(2)))

        return image, description
    except Exception:
        return None, None


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
telegram_news = []       # NO LINKS -- posted to the public channel (combined digest, now with real paragraphs)
personal_articles = []   # WITH LINKS + image -- one Telegram post per article
file_news = []           # WITH LINKS -- written to the local artifact file
new_links = set()
counter = 1

for site in SITES:
    print(f"🔎 Scraping: {site['name']}")
    articles = scrape_site(site)
    print(f"   found {len(articles)} article link(s)")

    for title, url in articles:
        if url in sent_links or url in new_links:
            continue

        image_url, description = fetch_article_meta(url)

        # TELEGRAM (NO LINKS) -- real short paragraph when available
        desc_line = f"   {description}\n" if description else ""
        telegram_news.append(
            f"{counter}. {title}\n"
            f"{desc_line}"
            f"   Source: {site['name']}"
        )

        # PERSONAL CHAT (WITH LINKS + image)
        personal_articles.append({
            "title": title,
            "published": f"{site['name']}, {DISPLAY_DATE}",
            "link": url,
            "image": image_url,
        })

        # FILE (WITH LINKS)
        file_news.append(
            f"{counter}. {title}\n"
            f"{desc_line}"
            f"   Source: {site['name']}\n"
            f"   Link: {url}\n"
        )

        new_links.add(url)
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
    chunks = []
    current = []
    current_len = len(header)
    for item in items:
        item_len = len(item) + 2
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
if SEND_TO_TELEGRAM and TELEGRAM_PERSONAL_CHAT_ID:
    if personal_articles:
        for art in personal_articles:
            caption = f"{art['title']}\n{art['published']}\nLink: {art['link']}"
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
