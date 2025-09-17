#!/usr/bin/env python3
"""
app.py - BOT MONITOR LELANG JBA

Versi ini:
 - Tambah WebDriverWait agar Selenium tidak ambil page_source terlalu cepat.
 - Kalau elemen tidak ketemu, tetap simpan page_source untuk debug.
"""

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================
# KONFIG TELEGRAM
# ==========================
BOT_TOKEN = os.getenv("BOT_TOKEN") or "ISI_TOKEN_MU"
CHAT_ID = os.getenv("CHAT_ID") or "ISI_CHATID_MU"

# ==========================
# KONFIG JBA
# ==========================
BASE_URL = "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword=&page={}"

# ==========================
# SETUP SELENIUM
# ==========================
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

# ==========================
# KUMPUL LOT
# ==========================
def get_lots_from_page(page: int):
    url = BASE_URL.format(page)
    print(f"[INFO] Buka halaman {page}: {url}")
    driver.get(url)
    try:
        # tunggu max 15 detik sampai minimal 1 vehicle-item muncul
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.vehicle-item"))
        )
    except Exception as e:
        print(f"[WARNING] Tidak menemukan lot di halaman {page} ({e})")

    # simpan untuk debug
    html = driver.page_source
    debug_file = f"debug_page_{page}.html"
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[DEBUG] Source halaman disimpan ke {debug_file}")

    soup = BeautifulSoup(html, "html.parser")
    lots = soup.select("div.vehicle-item")
    return lots

# ==========================
# KIRIM TELEGRAM
# ==========================
def send_telegram(msg: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        if r.status_code != 200:
            print(f"[ERROR] Gagal kirim Telegram: {r.text}")
    except Exception as e:
        print(f"[ERROR] Exception kirim Telegram: {e}")

# ==========================
# MAIN
# ==========================
def main():
    start = datetime.now()
    print(f"[{start}] Mulai bot JBA filter KB")

    semua_lot = []
    for page in [1, 6]:  # contoh: ambil page 1 & 6
        lots = get_lots_from_page(page)
        if not lots:
            print(f"[WARNING] Halaman {page} kosong")
            continue
        for lot in lots:
            title = lot.get_text(strip=True)
            semua_lot.append(title)

    if semua_lot:
        pesan = "🚨 Lot ditemukan:\n" + "\n".join(semua_lot)
        send_telegram(pesan)
    else:
        print("[INFO] Tidak ada lot baru")

    selesai = datetime.now()
    print(f"[{selesai}] Selesai")

if __name__ == "__main__":
    main()
    driver.quit()
