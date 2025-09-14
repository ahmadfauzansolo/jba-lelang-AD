import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# =========================================
# LOAD ENV
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword="

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# SETUP SELENIUM CHROME HEADLESS
# =========================================
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

# =========================================
# GET ALL LOTS
# =========================================
def get_all_lots():
    all_lots = []
    page = 1
    while True:
        url = f"{BASE_URL}&page={page}"
        driver.get(url)
        time.sleep(3)  # tunggu JS load

        lots = driver.find_elements(By.CSS_SELECTOR, "div.vehicle-item")
        if not lots:
            print(f"[INFO] Tidak ada lot di halaman {page}, berhenti. Ini halaman terakhir.")
            break

        for lot in lots:
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

            all_lots.append({
                "title": title,
                "location": location,
                "plate": plate,
                "link": link,
                "photo": img_url
            })

        print(f"[INFO] Halaman {page}: Ditemukan {len(lots)} lot")
        page += 1

    print(f"[INFO] Total lot ditemukan: {len(all_lots)}")
    return all_lots

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
                res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
                print(f"[INFO] Lot terkirim dengan foto, status {res.status_code}")
                return
        except Exception as e:
            print(f"[ERROR] Gagal kirim foto: {e}")

    # fallback tanpa foto
    res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"})
    print(f"[INFO] Lot terkirim tanpa foto, status {res.status_code}")

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")
    lots = get_all_lots()
    for lot in lots:
        send_message(lot)
    print(f"[{datetime.now()}] Bot selesai.")

if __name__ == "__main__":
    main()
