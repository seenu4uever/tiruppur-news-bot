import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

print("🚀 Script started")

# ================= TIME =================
file_date = datetime.now().strftime("%d-%m-%Y")
timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")

# ================= PATH =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(BASE_DIR, "news_output")
os.makedirs(folder_path, exist_ok=True)

file_path = os.path.join(folder_path, f"tiruppur_news_raw_{file_date}.txt")

# ================= CREATE FILE =================
with open(file_path, "w", encoding="utf-8") as f:
    f.write(f"Timestamp: {timestamp}\n\nRaw data:\n\n")

print("📄 File created:", file_path)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ================= WEBSITES =================
websites = [
    {
        "name": "Dinamalar",
        "url": "https://www.dinamalar.com/news/tamil-nadu-district-news-tiruppur",
        "base": "https://www.dinamalar.com",
        "tag": "p",
        "must_contain": "district-news-tiruppur/",
        "limit": 12
    },
    {
        "name": "Dinamani",
        "url": "https://www.dinamani.com/all-editions/edition-coimbatore/tiruppur",
        "base": "https://www.dinamani.com",
        "tag": "h2",
        "must_contain": "/tiruppur/",
        "limit": 12
    }
]

# ================= SCRAPING =================
with open(file_path, "a", encoding="utf-8") as file:
    for site in websites:
        print(f"🔎 Fetching {site['name']}")
        file.write(f"{site['name']}:\n\n")

        try:
            r = requests.get(site["url"], headers=HEADERS, timeout=20)
        except Exception as e:
            file.write("Request failed\n\n")
            print("❌ Request failed:", e)
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        count = 0
        seen = set()

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

            if site["must_contain"] not in full_url:
                continue

            if full_url in seen:
                continue

            seen.add(full_url)
            file.write(f"{title} - {full_url}\n\n")
            count += 1

        if count == 0:
            file.write("No news found\n\n")

print("🎉 DONE")
print("📄 Output saved at:", file_path)
