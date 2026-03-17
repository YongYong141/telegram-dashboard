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

# --- 1. PAGE CONFIG & DARK THEME ---
st.set_page_config(page_title="Guatemala KPI Master", page_icon="🌙", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #020617; color: #f8fafc; }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    .stTable { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
    thead tr th { background-color: #334155 !important; color: #38bdf8 !important; }
    .stButton>button { border-radius: 10px; background-color: #0ea5e9; color: white; border: none; font-weight: bold; width: 100%; height: 45px; }
    .stButton>button:hover { background-color: #38bdf8; transform: translateY(-2px); }
    [data-testid="stSidebar"] { background-color: #0f172a !important; border-right: 1px solid #334155; }
    h1, h2, h3 { color: #38bdf8 !important; text-align: center; }
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

# --- 3. TELEGRAM LOGIC (FULL FIX WITH 2FA) ---
async def telegram_worker(phone, nickname, code=None, h_hash=None, password=None):
    session = f'session_{phone.replace("+","").strip()}'
    client = TelegramClient(session, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if code:
                try:
                    await client.sign_in(phone, code, phone_code_hash=h_hash)
                except errors.SessionPasswordNeededError:
                    if password:
                        await client.sign_in(password=password)
                    else:
                        return "2FA_NEEDED"
            else:
                sent = await client.send_code_request(phone)
                return sent.phone_code_hash
        
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        save_db(db)

        # A. စာအသစ်ဝင်လျှင် Leads တိုးခြင်း
        @client.on(events.NewMessage(incoming=True))
        async def incoming_handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return
                
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)
                
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

        # B. Delete Chat Check (၅ မိနစ်တစ်ခါ)
        while True:
            await asyncio.sleep(300) 
            db_chk = load_db()
            if phone in db_chk['staff_data']:
                current_list = db_chk['staff_data'][phone]['customers'][:]
                for c_id in current_list:
                    try:
                        await client.get_input_entity(c_id)
                    except:
                        # Chat ပျောက်သွားရင်/Block သွားရင် နုတ်မယ်
                        db_chk['staff_data'][phone]['customers'].remove(c_id)
                        if c_id in db_chk['global_customers']: db_chk['global_customers'].remove(c_id)
                        db_chk['total_deleted'] += 1
                        if c_id in db_chk['staff_data'][phone]['depositors']:
                            db_chk['staff_data'][phone]['depositors'].remove(c_id)
                            db_chk['total_deposits'] = max(0, db_chk['total_deposits'] - 1)
                save_db(db_chk)

    except Exception as e: return str(e)
    finally: await client.disconnect()

def start_thread(phone, nickname):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    threading.Thread(target=run, daemon=True).start()

# --- 4. MAIN UI ---
db = load_db()

with st.sidebar:
    st.title("🛡️ Admin Panel")
    ph = st.text_input("Phone Number")
    nk = st.text_input("Nickname")
    
    if "h_hash" not in st.session_state:
        if st.button("🚀 Get OTP Code"):
            res = asyncio.run(telegram_worker(ph, nk))
            if isinstance(res, str) and len(res) > 20: 
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(f"Error: {res}")
    else:
        otp = st.text_input("Enter OTP Code")
        pw = st.text_input("2FA Password (If any)", type="password")
        if st.button("✅ Link & Start"):
            f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
            if f is None or f == "Online 🟢":
                start_thread(ph, nk); st.success("Connected!"); del st.session_state.h_hash; st.rerun()
            elif f == "2FA_NEEDED": st.warning("Please enter your 2FA Password.")
            else: st.error(f)

# DASHBOARD HEADER & METRICS
st.title("⭐ GUATEMALA KPI MASTER ⭐")
leads = len(db['global_customers'])
deps = db['total_deposits']
conv = (deps / leads * 100) if leads > 0 else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 GLOBAL LEADS", leads)
m2.metric("💰 TOTAL DEPOSITS", deps)
m3.metric("📊 CONVERSION %", f"{conv:.1f}%")
m4.metric("🗑️ DELETE CHATS", db.get('total_deleted', 0))

st.markdown("---")

col_table, col_mgmt = st.columns([1.8, 1])

with col_table:
    st.subheader("👨‍💼 Staff Status")
    rows = []
    for p, s in db['staff_data'].items():
        l, d = len(s['customers']), len(s['depositors'])
        rows.append({"Staff": s['nickname'], "Phone": p, "Leads": l, "Deps": d, "Conv%": f"{(d/l*100 if l>0 else 0):.1f}%"})
    if rows: st.table(pd.DataFrame(rows))
    else: st.info("Waiting for staff...")

with col_mgmt:
    st.subheader("🛠️ Management")
    staff_map = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    if staff_map:
        selected = st.selectbox("Select Account", list(staff_map.keys()))
        target = staff_map[selected]
        
        c1, c2 = st.columns(2)
        if c1.button("➖ Delete Lead"):
            if db['staff_data'][target]['customers']:
                db['staff_data'][target]['customers'].pop()
                db['total_deleted'] += 1; save_db(db); st.rerun()
        if c2.button("📉 Deduct Dep"):
            if db['staff_data'][target]['depositors']:
                db['staff_data'][target]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()

        if st.button("🚪 Logout Selected Account Only", type="primary"):
            del db['staff_data'][target]; save_db(db); st.rerun()

    if st.button("🧹 Reset All Numbers"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']: db['staff_data'][p].update({'customers': [], 'depositors': []})
        save_db(db); st.rerun()
