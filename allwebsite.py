import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os

print("🚀 Script started")

# ================= FLAGS (TESTING SAFE) =================
SAVE_TO_FILE = False        # Set True if you want a txt file locally
SEND_TO_TELEGRAM = False   # Keep False during testing

# ================= TIME (IST) =================
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)

today_date = now_ist.strftime("%d-%m-%Y")
timestamp = now_ist.strftime("%d-%m-%Y %I:%M %p IST")

# ================= HEADERS =================
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ================= DEDUP FILE (SIMULATES GITHUB ARTIFACT) =================
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

# ================= OUTPUT =================
output_text = f"Timestamp: {timestamp}\n\nRaw data:\n\n"
news_count = 0
new_links_added = False

# ================= SCRAPING =================
for site in websites:
    print(f"🔎 Fetching {site['name']}")
    output_text += f"{site['name']}:\n\n"

    try:
        r = requests.get(site["url"], headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception:
        output_text += "Request failed\n\n"
        continue

    soup = BeautifulSoup(r.text, "html.parser")
    site_new_count = 0

    for a in soup.find_all("a", href=True):
        if site_new_count >= site["limit"]:
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

        # ===== GLOBAL DEDUP =====
        if full_url in sent_links:
            continue

        sent_links.add(full_url)
        new_links_added = True

        output_text += f"{title} - {full_url}\n\n"
        site_new_count += 1
        news_count += 1

    if site_new_count == 0:
        output_text += "No new news found\n\n"

# ================= SAVE DEDUP FILE =================
if new_links_added:
    with open(DEDUP_FILE, "w", encoding="utf-8") as f:
        for link in sorted(sent_links):
            f.write(link + "\n")

# ================= OPTIONAL FILE SAVE =================
if SAVE_TO_FILE:
    folder_path = "news_output"
    os.makedirs(folder_path, exist_ok=True)
    file_path = os.path.join(folder_path, f"tiruppur_news_raw_{today_date}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output_text)
    print("📄 File created:", file_path)

# ================= FINAL OUTPUT =================
print("\n================ OUTPUT ================\n")
print(output_text.strip())
print("\n========================================")

if news_count == 0:
    print("ℹ️ No new news found (dedup working correctly)")
else:
    print(f"✅ {news_count} new news item(s) found")

print("✅ Script finished cleanly")
