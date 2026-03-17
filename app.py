import streamlit as st
from telethon import TelegramClient, events, errors, functions
import asyncio
import threading
import json
import os
import pandas as pd
from streamlit_autorefresh import st_autorefresh
import io
from PIL import Image
import pytesseract

# --- 1. CONFIG & DARK THEME ---
st.set_page_config(page_title="KPI Deep Dark Pro", page_icon="🌙", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
    }
    .stTable { background-color: #1e293b; border-radius: 12px; }
    .stButton>button { border-radius: 10px; background-color: #0ea5e9; color: white; width: 100%; height: 45px; }
    [data-testid="stSidebar"] { background-color: #0f172a !important; border-right: 1px solid #1e293b; }
    h1, h2, h3 { color: #38bdf8 !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- 2. DATABASE ---
DB_FILE = 'dashboard_data.json'
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

# --- 3. TELEGRAM LOGIC (DELETE CHAT CHECK) ---
async def telegram_worker(phone, nickname, code=None, h_hash=None):
    api_id, api_hash = 38792395, '4e8e3896fb5b1960993eec6a36c1b932'
    session = f'session_{phone.replace("+","").strip()}'
    client = TelegramClient(session, api_id, api_hash)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if code: await client.sign_in(phone, code, phone_code_hash=h_hash)
            else: return await client.send_code_request(phone)
        
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        save_db(db)

        # (A) စာအသစ်ဝင်လျှင် Leads တိုးမည့်အပိုင်း
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return
                
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)
                
                # Image/OCR logic as before...
                save_db(db_now)

        # (B) Delete Chat စစ်ဆေးသည့်အပိုင်း (Background Task)
        # ၅ မိနစ်တစ်ခါ Customer List ကို စစ်ပြီး Chat မရှိတော့ရင် စာရင်းကနေ နုတ်ပါမယ်
        while True:
            await asyncio.sleep(300) # 5 mins check
            db_chk = load_db()
            if phone in db_chk['staff_data']:
                current_customers = db_chk['staff_data'][phone]['customers'][:]
                for c_id in current_customers:
                    try:
                        # Chat ရှိသေးလား စစ်ဆေးခြင်း
                        await client.get_input_entity(c_id)
                    except (ValueError, errors.PeerIdInvalidError):
                        # Chat မရှိတော့လျှင် (Delete Chat) စာရင်းမှနုတ်ခြင်း
                        db_chk['staff_data'][phone]['customers'].remove(c_id)
                        if c_id in db_chk['global_customers']:
                            db_chk['global_customers'].remove(c_id)
                        db_chk['total_deleted'] += 1
                save_db(db_chk)

    except: pass
    finally: await client.disconnect()

def start_thread(phone, nickname):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    threading.Thread(target=run, daemon=True).start()

# --- 4. DASHBOARD UI ---
db = load_db()

with st.sidebar:
    st.title("🛡️ Admin Portal")
    ph = st.text_input("Phone")
    nk = st.text_input("Nickname")
    if "h_hash" not in st.session_state:
        if st.button("🚀 Get OTP"):
            res = asyncio.run(telegram_worker(ph, nk))
            st.session_state.h_hash = res.phone_code_hash; st.success("OTP Sent!")
    else:
        otp = st.text_input("OTP")
        if st.button("✅ Connect"):
            asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash))
            start_thread(ph, nk); st.rerun()

st.markdown("<h1 style='text-align: center;'>⭐ GUATEMALA PREMIUM DARK ⭐</h1>", unsafe_allow_html=True)

# Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 GLOBAL LEADS", len(db['global_customers']))
m2.metric("💰 TOTAL DEPOSITS", db['total_deposits'])
m3.metric("🔞 UNDER-AGE", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ DELETE CHATS", db.get('total_deleted', 0))

st.markdown("---")

# Management
c_left, c_right = st.columns([1.5, 1])
with c_left:
    st.subheader("👨‍💼 Team Status")
    rows = [{"Staff": s['nickname'], "Phone": p, "Leads": len(s['customers']), "Deps": len(s['depositors'])} for p, s in db['staff_data'].items()]
    if rows: st.table(pd.DataFrame(rows))

with c_right:
    st.subheader("🛠️ Management")
    options = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    if options:
        selected = st.selectbox("Select Account", list(options.keys()))
        target = options[selected]
        
        # တစ်ယောက်ချင်း Logout လုပ်ရန် (သေသပ်စွာ လုပ်ထားသည်)
        if st.button("🚪 Logout Selected Account Only", type="primary"):
            del db['staff_data'][target]
            save_db(db); st.rerun()

    if st.button("🧹 Reset All Numbers"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']: db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()
