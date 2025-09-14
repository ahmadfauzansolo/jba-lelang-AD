# =========================================
# APP.PY - BOT MONITOR LELANG JBA MOTOR PLAT AD
# =========================================
import requests, json, os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEEN_FILE = "seen_api.json"
JBA_URL = "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword="

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

# =========================================
# HELPERS
# =========================================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            seen = set(json.load(f))
        print(f"[INFO] Loaded {len(seen)} lot dari seen_api.json")
        return seen
    except FileNotFoundError:
        print("[INFO] seen_api.json tidak ditemukan, membuat baru")
        return set()
    except Exception as e:
        print(f"[ERROR] Gagal load seen_api.json: {e}")
        return set()

def save_seen(seen):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen), f, ensure_ascii=False, indent=2)
        print(f"[INFO] Disimpan {len(seen)} lot ke seen_api.json")
    except Exception as e:
        print(f"[ERROR] Gagal simpan seen_api.json: {e}")

# =========================================
# SCRAPING JBA
# =========================================
def get_ad_lots():
    try:
        r = requests.get(JBA_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        lots = soup.find_all("div", class_="vehicle-item")

        ad_lots = []
        for lot in lots:
            plate = lot.find("span", class_="plate-number")
            if plate and plate.text.strip().startswith("AD"):
                lot_id = lot.get("data-id") or lot.get("id") or plate.text.strip()
                title = lot.find("h4").text.strip()
                location_tag = lot.find("span", class_="location")
                location = location_tag.text.strip() if location_tag else "(tidak diketahui)"
                link_tag = lot.find("a", href=True)
                link = f"https://www.jba.co.id{link_tag['href']}" if link_tag else "#"
                ad_lots.append({
                    "id": lot_id,
                    "title": title,
                    "location": location,
                    "plate": plate.text.strip(),
                    "link": link
                })
        print(f"[INFO] Ditemukan {len(ad_lots)} lot plat AD")
        return ad_lots
    except Exception as e:
        print(f"[ERROR] Gagal ambil data dari JBA: {e}")
        return []

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
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"}
        )
        print(f"[INFO] Lot {lot['id']} terkirim ke Telegram, status {res.status_code}")
    except Exception as e:
        print(f"[ERROR] Gagal kirim lot {lot['id']} ke Telegram: {e}")

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")
    seen = load_seen()
    new_count = 0

    lots = get_ad_lots()
    for lot in lots:
        lot_id = lot['id']
        if lot_id in seen:
            continue
        send_message(lot)
        seen.add(lot_id)
        new_count += 1

    save_seen(seen)
    print(f"[INFO] {new_count} lot baru terkirim")
    print(f"[{datetime.now()}] Bot selesai.")

if __name__ == "__main__":
    main()
