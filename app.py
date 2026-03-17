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

# --- 1. THEME & CONFIG ---
st.set_page_config(page_title="Guatemala KPI Pro", page_icon="🌙", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    .stTable { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
    thead tr th { background-color: #334155 !important; color: #38bdf8 !important; }
    .stButton>button { border-radius: 10px; background-color: #0ea5e9; color: white; border: none; font-weight: bold; width: 100%; height: 45px; }
    .stButton>button:hover { background-color: #38bdf8; transform: translateY(-2px); }
    [data-testid="stSidebar"] { background-color: #0f172a !important; border-right: 1px solid #334155; }
    h1, h2, h3 { color: #38bdf8 !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- 2. CONSTANTS & DATABASE ---
API_ID = 38792395
API_HASH = '4e8e3896fb5b1960993eec6a36c1b932'
DB_FILE = 'dashboard_data.json'
BANK_KEYWORDS = ["banrural", "industrial", "g&t", "azteca", "bac", "bantrab", "promerica", "bam", "transferencia", "monto", "exitoso", "comprobante"]

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return default_db()
    return default_db()

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def default_db():
    return {'global_customers': [], 'staff_data': {}, 'total_deleted': 0, 'total_deposits': 0}

# --- 3. TELEGRAM BACKGROUND LOGIC ---
async def telegram_worker(phone, nickname, code=None, hash=None):
    session = f'session_{phone.replace("+","").strip()}'
    client = TelegramClient(session, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if code:
                await client.sign_in(phone, code, phone_code_hash=hash)
            else:
                sent = await client.send_code_request(phone)
                return sent.phone_code_hash
        
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        save_db(db)

        # A. စာအသစ်ဝင်ရင် Lead ပေါင်းခြင်း
        @client.on(events.NewMessage(incoming=True))
        async def incoming_handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return
                
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)

                # OCR / Age check logic
                msg = (event.message.message or "").lower()
                if any(x in msg for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)
                
                if event.photo:
                    try:
                        photo_bytes = await event.download_media(file=bytes)
                        img = Image.open(io.BytesIO(photo_bytes))
                        txt = pytesseract.image_to_string(img).lower()
                        if any(k in txt for k in BANK_KEYWORDS):
                            if u_id not in db_now['staff_data'][phone]['depositors']:
                                db_now['staff_data'][phone]['depositors'].append(u_id)
                                db_now['total_deposits'] += 1
                    except: pass
                save_db(db_now)

        # B. Chat တစ်ခုလုံးဖျက်သွားခြင်းကို စစ်ဆေးခြင်း (Delete Chat Check)
        # ၅ မိနစ်တစ်ခါ Customer စာရင်းကို loop ပတ်ပြီး Chat ရှိသေးလား စစ်ပါမယ်
        while True:
            await asyncio.sleep(300) 
            db_chk = load_db()
            if phone in db_chk['staff_data']:
                active_list = db_chk['staff_data'][phone]['customers'][:]
                for c_id in active_list:
                    try:
                        await client.get_input_entity(c_id)
                    except (ValueError, errors.PeerIdInvalidError):
                        # Chat မရှိတော့ရင် (Delete Chat လုပ်သွားရင်) စာရင်းမှ နုတ်မယ်
                        db_chk['staff_data'][phone]['customers'].remove(c_id)
                        if c_id in db_chk['global_customers']:
                            db_chk['global_customers'].remove(c_id)
                        db_chk['total_deleted'] += 1
                save_db(db_chk)

    except: pass
    finally: await client.disconnect()

def start_thread(phone, nickname):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    threading.Thread(target=run_loop, daemon=True).start()

# --- 4. MAIN DASHBOARD ---
db = load_db()

with st.sidebar:
    st.title("🛡️ Admin Portal")
    ph_in = st.text_input("Phone Number")
    nk_in = st.text_input("Nickname")
    if "h_hash" not in st.session_state:
        if st.button("🚀 Get OTP"):
            res = asyncio.run(telegram_worker(ph_in, nk_in))
            st.session_state.h_hash = res; st.success("OTP Sent!")
    else:
        otp_in = st.text_input("OTP Code")
        if st.button("✅ Link Account"):
            asyncio.run(telegram_worker(ph_in, nk_in, otp_in, st.session_state.h_hash))
            start_thread(ph_in, nk_in); st.success("Linked!"); del st.session_state.h_hash

st.markdown("<h1 style='text-align: center;'>⭐ GUATEMALA PREMIUM DARK MODE ⭐</h1>", unsafe_allow_html=True)

# Metrics Grid
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 GLOBAL LEADS", len(db['global_customers']))
m2.metric("💰 TOTAL DEPOSITS", db['total_deposits'])
m3.metric("🔞 UNDER-AGE", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ DELETE CHATS", db.get('total_deleted', 0))

st.markdown("---")

c_left, c_right = st.columns([1.6, 1])

with c_left:
    st.subheader("👨‍💼 Team Status")
    rows = []
    for p, s in db['staff_data'].items():
        rows.append({"Staff": s['nickname'], "Phone": p, "Leads": len(s['customers']), "Deps": len(s['depositors'])})
    if rows: st.table(pd.DataFrame(rows))
    else: st.info("No active accounts.")

with c_right:
    st.subheader("🛠️ Management Console")
    options = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    if options:
        selected = st.selectbox("Select Account", list(options.keys()))
        target = options[selected]

        # တစ်ယောက်ချင်း Logout လုပ်ခြင်း
        if st.button("🚪 Logout Selected Account Only", type="primary"):
            if target in db['staff_data']:
                del db['staff_data'][target]
                save_db(db); st.rerun()

    st.markdown("---")
    if st.button("🧹 Reset All Numbers (Keep Accounts)"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']: db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()

    if st.sidebar.button("💀 Full System Wipeout"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()
