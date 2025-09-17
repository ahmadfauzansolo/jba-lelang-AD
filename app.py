#!/usr/bin/env python3
"""
jba_ad_bot.py

Bot scraper untuk JBA (lelang motor) — mengirim ke Telegram hanya lot dengan plat "AD".
Fitur:
 - Scrape list halaman (pagination)
 - Buka halaman detail tiap lot untuk ambil "Nomor Polisi"
 - Kirim ke Telegram (sendPhoto jika ada foto, fallback ke sendMessage)
 - Simpan lot yang sudah dikirim ke file `sent_lots.json` untuk menghindari pengiriman duplikat
 - Robust: WebDriverWait, retry download gambar, beberapa fallback XPATH untuk ambil plat

Cara pakai:
 - Buat file .env dengan TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID
 - Pastikan chromedriver tersedia dan versi cocok dengan Chrome/Chromium
 - Install deps: pip install selenium python-dotenv requests
 - Jalankan: python jba_ad_bot.py

Catatan: script dibuat supaya teliti tapi lingkungan website bisa berubah — jika ada error di selector,
sementara ubah XPATH di `PLATE_XPATH_CANDIDATES`.
"""

import os
import time
import json
import re
import html
import tempfile
import shutil
import requests
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ============ CONFIG ============
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = os.getenv("BASE_URL", "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword=")
SENT_FILE = os.getenv("SENT_FILE", "sent_lots.json")
MAX_PAGES = int(os.getenv("MAX_PAGES", "50"))  # safety limit
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "1.5"))  # detik antar pesan ke Telegram
HEADLESS = os.getenv("HEADLESS", "1") != "0"
CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")  # kosong -> webdriver.Chrome() default

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise SystemExit("ENV error: set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di .env")

# XPATH candidates untuk mencoba ambil Nomor Polisi / Plat
PLATE_XPATH_CANDIDATES = [
    "//div[normalize-space(text())='Nomor Polisi']/following-sibling::div[1]",
    "//div[contains(normalize-space(.),'Nomor Polisi')]/following-sibling::div[1]",
    "//th[normalize-space(text())='Nomor Polisi']/following-sibling::td[1]",
    "//label[normalize-space(text())='Nomor Polisi']/following-sibling::*[1]",
    # fallback: cari elemen yang mengandung 'Nomor Polisi' lalu ambil dan parse teksnya
]

# ============ HELPERS ============

def load_sent(filename: str):
    try:
        if not os.path.exists(filename):
            return set()
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data if isinstance(data, list) else [])
    except Exception as e:
        print(f"[WARN] Gagal load sent file: {e}")
        return set()


def save_sent(sent_set: set, filename: str):
    try:
        tmpfd, tmpname = tempfile.mkstemp(prefix="sent_", suffix=".json")
        with os.fdopen(tmpfd, "w", encoding="utf-8") as tmpf:
            json.dump(sorted(list(sent_set)), tmpf, indent=2, ensure_ascii=False)
        shutil.move(tmpname, filename)
    except Exception as e:
        print(f"[ERROR] Gagal simpan sent file: {e}")


def sanitize_plate(plate: str) -> str:
    if not plate:
        return ""
    p = plate.upper().strip()
    # keep only alnum (huruf + angka), hapus spasi dan karakter lain
    p = re.sub(r"[^A-Z0-9]", "", p)
    return p


def ensure_absolute_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://www.jba.co.id" + url
    return url


# ============ SELENIUM SETUP ============

def make_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # beberapa website mendeteksi headless; user-agent bisa di-set jika perlu
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    if CHROME_DRIVER_PATH:
        return webdriver.Chrome(executable_path=CHROME_DRIVER_PATH, options=options)
    else:
        return webdriver.Chrome(options=options)


# ============ SCRAPING ============

def get_all_lots(driver, max_pages=MAX_PAGES):
    all_lots = []
    page = 1
    while page <= max_pages:
        url = f"{BASE_URL}&page={page}"
        print(f"[INFO] Buka halaman list: {url}")
        try:
            driver.get(url)
        except Exception as e:
            print(f"[WARN] Gagal load halaman list {url}: {e}")
            break

        # tunggu ada setidaknya satu item (beri fallback ke sleep kecil)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.vehicle-item"))
            )
        except Exception:
            # beri sedikit waktu ekstra, lalu cek apakah ada items
            time.sleep(2)

        # ambil items, coba beberapa selector bila perlu
        lots_elems = driver.find_elements(By.CSS_SELECTOR, "div.vehicle-item")
        if not lots_elems:
            lots_elems = driver.find_elements(By.CSS_SELECTOR, "div.listing-item")

        if not lots_elems:
            print(f"[INFO] Tidak menemukan lot di halaman {page}. Hentikan loop.")
            break

        for lot in lots_elems:
            try:
                title = lot.find_element(By.CSS_SELECTOR, "h4").text.strip()
            except Exception:
                title = "(tanpa judul)"
            try:
                location = lot.find_element(By.CSS_SELECTOR, "span.location").text.strip()
            except Exception:
                # fallback cari kata 'Lokasi' di text
                try:
                    location = lot.text.split('\n')[-1]
                except Exception:
                    location = "(tidak diketahui)"
            try:
                a = lot.find_element(By.CSS_SELECTOR, "a")
                link = ensure_absolute_url(a.get_attribute("href"))
            except Exception:
                link = None
            try:
                img = lot.find_element(By.CSS_SELECTOR, "img").get_attribute("src")
                img = ensure_absolute_url(img)
            except Exception:
                img = None

            all_lots.append({
                "title": title,
                "location": location,
                "link": link,
                "photo": img,
            })

        print(f"[INFO] Halaman {page}: Ditemukan {len(lots_elems)} lot")
        page += 1
        # beri jeda kecil supaya tidak membebani server
        time.sleep(0.6)

    print(f"[INFO] Total lot ditemukan: {len(all_lots)}")
    return all_lots


def get_plate_from_detail(driver, link: str) -> str:
    if not link:
        return None
    try:
        driver.get(link)
    except Exception as e:
        print(f"[WARN] Gagal buka detail {link}: {e}")
        return None

    # tunggu sedikit sampai konten detail muncul
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(.), 'Nomor Polisi')]") )
        )
    except Exception:
        # lanjut saja: mungkin label muncul dalam struktur berbeda
        pass

    # coba beberapa XPATH kandidat
    for xp in PLATE_XPATH_CANDIDATES:
        try:
            el = driver.find_element(By.XPATH, xp)
            text = el.text.strip()
            if text:
                return text
        except Exception:
            continue

    # fallback: cari elemen yang mengandung 'Nomor Polisi' lalu parse teks (contoh: 'Nomor Polisi: BH 2944 VX')
    els = driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'Nomor Polisi')]")
    for el in els:
        t = el.text.strip()
        # cari pola setelah kata Nomor Polisi
        m = re.search(r"Nomor\s*Polisi[:\s]*([^\n]+)", t, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # terkadang label dan value anak terpisah -> cek sibling
        try:
            sib = el.find_element(By.XPATH, "following-sibling::*[1]")
            if sib and sib.text.strip():
                return sib.text.strip()
        except Exception:
            pass

    # jika tetap tidak ketemu, kembalikan None
    return None


# ============ TELEGRAM SENDING ============

def download_image(url: str, max_retries=3):
    if not url:
        return None
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200 and r.content:
                return r.content
            else:
                print(f"[WARN] Download image status {r.status_code} (attempt {attempt})")
        except Exception as e:
            print(f"[WARN] Error download image (attempt {attempt}): {e}")
        time.sleep(1 + attempt * 0.5)
    return None


def send_message(lot: dict, plate_raw: str):
    title_html = html.escape(lot.get('title') or "(tanpa judul)")
    location_html = html.escape(lot.get('location') or "(tidak diketahui)")
    plate_html = html.escape(plate_raw or "-")
    link = lot.get('link') or ""

    caption = f"{title_html}\n📍 Lokasi: {location_html}\n🏷 Plat: {plate_html}\n🔗 <a href='{link}'>Lihat detail lelang</a>"

    bot_base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    # coba kirim foto jika ada
    photo_url = lot.get('photo')
    if photo_url:
        img_data = download_image(photo_url)
        if img_data:
            try:
                files = {"photo": ("image.jpg", img_data)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                res = requests.post(f"{bot_base}/sendPhoto", data=data, files=files, timeout=30)
                if res.status_code == 200:
                    print(f"[INFO] Terkirim dengan foto: {lot.get('link')} (HTTP {res.status_code})")
                    return True
                else:
                    print(f"[WARN] sendPhoto gagal status {res.status_code}, fallback ke sendMessage")
            except Exception as e:
                print(f"[WARN] Exception saat sendPhoto: {e}")

    # fallback ke text message
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"}
        res = requests.post(f"{bot_base}/sendMessage", data=payload, timeout=20)
        if res.status_code == 200:
            print(f"[INFO] Terkirim tanpa foto: {lot.get('link')} (HTTP {res.status_code})")
            return True
        else:
            print(f"[ERROR] sendMessage gagal status {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Exception saat sendMessage: {e}")
        return False


# ============ MAIN ============

def main():
    print(f"[{datetime.now()}] Mulai bot JBA AD filter")
    driver = make_driver()
    sent = load_sent(SENT_FILE)
    print(f"[INFO] {len(sent)} lot sudah pernah dikirim (dari {SENT_FILE})")

    try:
        lots = get_all_lots(driver)
        for lot in lots:
            link = lot.get('link')
            if not link:
                print("[SKIP] Lot tanpa link, lewati")
                continue
            # identifikasi unik: gunakan seluruh link sebagai kunci
            key = link
            if key in sent:
                print(f"[SKIP] Sudah dikirim sebelumnya: {link}")
                continue

            plate_text = get_plate_from_detail(driver, link)
            if not plate_text:
                print(f"[SKIP] Plat tidak ditemukan di detail: {link}")
                continue

            normalized = sanitize_plate(plate_text)
            if normalized.startswith("AD"):
                print(f"[MATCH] Plat {plate_text} (normalized={normalized}) => akan dikirim")
                ok = send_message(lot, plate_text)
                if ok:
                    sent.add(key)
                    save_sent(sent, SENT_FILE)
                    # jeda supaya Telegram tidak menolak banyak kiriman cepat
                    time.sleep(MESSAGE_DELAY)
                else:
                    print(f"[WARN] Gagal kirim untuk {link}, tidak memasukkan ke sent list")
            else:
                print(f"[SKIP] Plat {plate_text} bukan AD (normalized={normalized})")

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print(f"[{datetime.now()}] Selesai")


if __name__ == '__main__':
    main()
