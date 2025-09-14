import requests, os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime

# =========================================
# LOAD ENV
# =========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JBA_URL = "https://www.jba.co.id/id/lelang-motor/search?vehicle_type=bike&keyword="

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise Exception("Set TELEGRAM_TOKEN dan TELEGRAM_CHAT_ID di environment variables!")

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

                # Ambil foto pertama (jika ada)
                img_tag = lot.find("img", src=True)
                img_url = img_tag['src'] if img_tag else None
                if img_url and not img_url.startswith("http"):
                    img_url = f"https://www.jba.co.id{img_url}"

                ad_lots.append({
                    "id": lot_id,
                    "title": title,
                    "location": location,
                    "plate": plate.text.strip(),
                    "link": link,
                    "photo": img_url
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
    # Kirim dengan foto jika ada
    if lot['photo']:
        try:
            img = requests.get(lot['photo'], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if img.status_code == 200:
                files = {"photo": ("img.jpg", img.content)}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", data=data, files=files)
                print(f"[INFO] Lot {lot['id']} terkirim dengan foto, status {res.status_code}")
                return
        except Exception as e:
            print(f"[ERROR] Gagal kirim foto lot {lot['id']}: {e}")
    # Fallback tanpa foto
    res = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                        data={"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "HTML"})
    print(f"[INFO] Lot {lot['id']} terkirim tanpa foto, status {res.status_code}")

# =========================================
# MAIN
# =========================================
def main():
    print(f"[{datetime.now()}] Bot mulai jalan...")
    lots = get_ad_lots()
    for lot in lots:
        send_message(lot)
    print(f"[{datetime.now()}] Bot selesai.")

if __name__ == "__main__":
    main()
