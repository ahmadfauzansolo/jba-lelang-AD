#!/usr/bin/env python3
import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================================
# LOAD ENV
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword="

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di .env!")

# =========================================
# SETUP SELENIUM CHROME HEADLESS
# =========================================
chrome_options = Options()
chrome_options.add_argument("--headless=new")  # new headless mode
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

# =========================================
# TELEGRAM
# =========================================
def send_message(lot):
    caption = (
        f"{lot['title']}\n"
        f"📍 Lokasi: {lot['location']}\n"
        f"🏷 Plat: {lot['plate']}\n"
        f"🔗 <a href='{lot['link']}'>Lihat detail lelang</a>"
    )
    if lot['photo']:
        try:
            img = requests.get(lot['photo'], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if img.status_code == 200:
                files = {"photo": ("img.jpg", img.content)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                                    data=data, files=files)
                print(f"[INFO] Lot terkirim (foto) status {res.status_code}")
                return
        except Exception as e:
            print(f"[ERROR] Gagal kirim foto: {e}")

    # fallback tanpa foto
    res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"})
    print(f"[INFO] Lot terkirim (teks) status {res.status_code}")

# =========================================
# SCRAPING
# =========================================
def get_lots_from_page(page):
    url = f"{BASE_URL}&page={page}"
    print(f"\n[INFO] Buka halaman {page}: {url}")
    driver.get(url)

    try:
        lots = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.vehicle-item, div.auction-item"))
        )
    except Exception as e:
        print(f"[WARNING] Tidak menemukan lot di halaman {page} ({e})")

        # simpan HTML buat debug
        debug_file = f"debug_page_{page}.html"
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"[DEBUG] Source halaman disimpan ke {debug_file}")

        return []

    page_lots = []
    for idx, lot in enumerate(lots, start=1):
        try:
            title = lot.find_element(By.CSS_SELECTOR, "h4").text.strip()
        except:
            title = "(tanpa judul)"

        try:
            location = lot.find_element(By.CSS_SELECTOR, "span.location").text.strip()
        except:
            location = "(tidak diketahui)"

        try:
            plate = lot.find_element(By.CSS_SELECTOR, "span.plate-number").text.strip()
        except:
            plate = "-"

        try:
            link_tag = lot.find_element(By.CSS_SELECTOR, "a")
            link = link_tag.get_attribute("href")
        except:
            link = "#"

        try:
            img_tag = lot.find_element(By.CSS_SELECTOR, "img")
            img_url = img_tag.get_attribute("src")
        except:
            img_url = None

        page_lots.append({
            "title": title,
            "location": location,
            "plate": plate,
            "link": link,
            "photo": img_url
        })

    return page_lots

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Mulai bot JBA filter KB")
    for page in [1, 6]:
        lots = get_lots_from_page(page)
        for lot in lots:
            plate = lot['plate'].upper().replace(" ", "")
            if plate.startswith("KB"):
                print(f"[MATCH] {lot['title']} | Plat: {lot['plate']}")
                send_message(lot)
            else:
                print(f"[SKIP] Plat: {lot['plate']}")
    print(f"[{datetime.now()}] Selesai")

if __name__ == "__main__":
    main()
    driver.quit()
