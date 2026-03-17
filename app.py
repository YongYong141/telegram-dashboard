import streamlit as st
from telethon import TelegramClient, events, errors
import asyncio
import threading
import json
import os
import pandas as pd
from streamlit_autorefresh import st_autorefresh
import io
from PIL import Image
import pytesseract

# --- CONFIGURATION ---
API_ID = 38792395
API_HASH = '4e8e3896fb5b1960993eec6a36c1b932'
DB_FILE = 'dashboard_data.json'
BANK_KEYWORDS = ["banrural", "industrial", "g&t", "azteca", "bac", "bantrab", "promerica", "bam", "transferencia", "monto", "exitoso", "comprobante"]

# --- DATABASE ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default_db()
    return default_db()

def default_db():
    return {'global_customers': [], 'staff_data': {}, 'total_deleted': 0, 'total_deposits': 0}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- TELEGRAM WORKER ---
async def telegram_worker(phone, nickname, code=None, hash=None, password=None):
    session_path = f'session_{phone.replace("+","").strip()}'
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if code:
                try:
                    await client.sign_in(phone, code, phone_code_hash=hash)
                except errors.SessionPasswordNeededError:
                    if password: await client.sign_in(password=password)
                    else: return "PASSWORD_NEEDED"
            else:
                sent = await client.send_code_request(phone)
                return sent.phone_code_hash

        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        save_db(db)

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return

                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)

                msg = (event.message.message or "").lower()
                if any(x in msg for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)

                if event.photo:
                    try:
                        photo_bytes = await event.download_media(file=bytes)
                        img = Image.open(io.BytesIO(photo_bytes))
                        # OCR စစ်ဆေးခြင်း
                        txt = pytesseract.image_to_string(img).lower()
                        if any(k in txt for k in BANK_KEYWORDS):
                            if u_id not in db_now['staff_data'][phone]['depositors']:
                                db_now['staff_data'][phone]['depositors'].append(u_id)
                                db_now['total_deposits'] += 1
                    except: pass
                save_db(db_now)
        await client.run_until_disconnected()
    except Exception as e: return str(e)
    finally: await client.disconnect()

def start_thread(phone, nickname):
    # Streamlit Cloud အတွက် thread ကို အခုလို သီးသန့် loop နဲ့ run ရပါမယ်
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    t = threading.Thread(target=run_async, daemon=True)
    t.start()

# --- STREAMLIT UI ---
st.set_page_config(page_title="KPI Dashboard", layout="wide")
st_autorefresh(interval=5000, key="refresh")
db = load_db()

st.title("🇬🇹 Guatemala KPI Dashboard")

# SideBar Login
with st.sidebar:
    st.header("🔐 Staff Login")
    ph_input = st.text_input("Phone (+95...)")
    nk_input = st.text_input("Nickname")
    
    if "h_hash" not in st.session_state:
        if st.button("Get OTP"):
            res = asyncio.run(telegram_worker(ph_input, nk_input))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res
                st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp_code = st.text_input("OTP Code")
        pw_2fa = st.text_input("2FA Password", type="password")
        if st.button("Login"):
            f = asyncio.run(telegram_worker(ph_input, nk_input, otp_code, st.session_state.h_hash, pw_2fa))
            if f is None:
                start_thread(ph_input, nk_input)
                st.success("Connected!")
                del st.session_state.h_hash
            else: st.error(f)

# Main Dashboard
c1, c2, c3 = st.columns(3)
c1.metric("Total Net Leads", len(db['global_customers']))
c2.metric("Verified Deposits", db['total_deposits'])
c3.metric("Under-age (15-19)", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))

st.markdown("---")
st.subheader("👨‍💼 Performance Table")
rows = []
for p, s in db['staff_data'].items():
    rows.append({
        "Staff": s['nickname'], 
        "Leads": len(s['customers']), 
        "Deposits": len(s['depositors']),
        "Under-age": len(s.get('under_age', []))
    })
if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Reset Button
if st.button("🧹 Reset Data Only"):
    db['global_customers'] = []; db['total_deposits'] = 0
    for p in db['staff_data']:
        db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
    save_db(db); st.rerun()
