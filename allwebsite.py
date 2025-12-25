from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

# ================= SILENCE CHROME LOGS =================
os.environ["WDM_LOG_LEVEL"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-gpu")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-webgl")
options.add_argument("--disable-software-rasterizer")
options.add_argument("--log-level=3")
options.add_experimental_option("excludeSwitches", ["enable-logging"])

service = Service(log_path=os.devnull)
driver = webdriver.Chrome(service=service, options=options)

# ================= DATE, TIME, PATH =================
today_date = datetime.now().strftime("%d-%m-%Y")
timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")

folder_path = r"C:\Users\Srini\pythonscript\news output"
os.makedirs(folder_path, exist_ok=True)

file_name = f"tiruppur_news_raw_{today_date}.txt"
file_path = os.path.join(folder_path, file_name)

# ================= WEBSITES =================
websites = [
    {
        "name": "Dinamalar",
        "url": "https://www.dinamalar.com/news/tamil-nadu-district-news-tiruppur",
        "base": "https://www.dinamalar.com",
        "tag": "p",
        "must_contain": "district-news-tiruppur/"
    },
    {
        "name": "Dinakaran",
        "url": "https://www.dinakaran.com/district/tiruppur",
        "base": "https://www.dinakaran.com",
        "tag": "h3",
        "must_contain": "/tiruppur/"
    },
    {
        "name": "Dinathanthi",
        "url": "https://www.dailythanthi.com/news/district/tirupur",
        "base": "https://www.dailythanthi.com",
        "tag": "span",
        "must_contain": "/tirupur/"
    },
    {
        "name": "Dinamani",
        "url": "https://www.dinamani.com/all-editions/edition-coimbatore/tiruppur",
        "base": "https://www.dinamani.com",
        "tag": "h2",
        "must_contain": "/tiruppur/"
    }
]

try:
    with open(file_path, "w", encoding="utf-8") as file:

        # ================= CHATGPT PROMPT HEADER =================
        file.write(
            "I will provide you with raw news data below in the following format:\n\n"
            "[Headline in Tamil] - [URL]\n\n"
            "For example:\n"
            "தீபாவளி பண்டிகைக்கான ஆர்டர்கள்.. அதிகரிப்பு: பின்னலாடை உற்பத்தியாளர் மகிழ்ச்சி - "
            "https://www.dinamalar.com/news/tamil-nadu-district-news-tiruppur/"
            "increase--orders-for-diwali-festival--knitwear-manufacturer-happy/4049049\n\n"
            "Please generate the output in **two formats**:\n\n"
            "1️⃣ **Without links:**\n"
            "- Remove website name at the end\n"
            "- Give me \"Without links\" in easy sharable format with bullet points\n"
            "- Give space between each news\n"
            "- Create a newspaper-style single-line news sentence in Tamil\n"
            "- Include today’s date at the top like:\n"
            "**நம்ம திருப்பூர் நியூஸ் - திருப்பூர் முக்கிய செய்திகள் - நாள் (today’s date)**\n\n"
            "2️⃣ **With links:**\n"
            "- Same format, but each news sentence should be a clickable link\n\n"
            "Output must be concise, smooth, and professional.\n"
            "Remove \"திருப்பூர்\" in Without Links (Copy & Share Friendly Format)\n\n"
            f"Timestamp: {timestamp}\n\n"
            "Raw data:\n\n"
        )

        # ================= RAW DATA =================
        for site in websites:
            file.write(f"{site['name']}:\n\n")

            driver.get(site["url"])
            time.sleep(6)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            found_news = False

            for a in soup.find_all("a", href=True):
                tag = a.find(site["tag"])
                if not tag:
                    continue

                title = tag.get_text(strip=True)
                if len(title) <= 10:
                    continue

                href = a["href"]
                full_url = href if href.startswith("http") else site["base"] + href

                if site["must_contain"] not in full_url:
                    continue

                file.write(f"{title} - {full_url}\n\n")
                found_news = True

            if not found_news:
                file.write("No news found\n\n")

finally:
    driver.quit()
