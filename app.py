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

# --- DARK MODE DESIGN ---
st.set_page_config(page_title="KPI Dark Dashboard", page_icon="🌙", layout="wide")

st.markdown("""
    <style>
    /* Dark Theme Core */
    .stApp { background-color: #0f172a; color: #f8fafc; }
    
    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 16px !important; }
    div[data-testid="stMetricValue"] { color: #38bdf8 !important; font-weight: bold !important; }

    /* Tables */
    .stTable { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
    thead tr th { background-color: #334155 !important; color: #38bdf8 !important; }
    
    /* Buttons */
    .stButton>button {
        border-radius: 10px;
        background-color: #0ea5e9;
        color: white;
        border: none;
        padding: 10px 24px;
        transition: 0.3s all;
    }
    .stButton>button:hover { background-color: #38bdf8; transform: translateY(-2px); }
    
    /* Sidebar Dark */
    [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
    
    /* Expander */
    .streamlit-expanderHeader { background-color: #1e293b !important; border-radius: 8px !important; border: 1px solid #334155 !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- DATABASE LOGIC (NO CHANGES) ---
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return default_db()
    return default_db()

def default_db():
    return {'global_customers': [], 'staff_data': {}, 'total_deleted': 0, 'total_deposits': 0}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

# --- TELEGRAM WORKER (NO CHANGES) ---
async def telegram_worker(phone, nickname, code=None, hash=None, password=None):
    session_path = f'session_{phone.replace("+","").strip()}'
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            if code:
                try: await client.sign_in(phone, code, phone_code_hash=hash)
                except errors.SessionPasswordNeededError:
                    if password: await client.sign_in(password=password)
                    else: return "PASSWORD_NEEDED"
            else:
                sent = await client.send_code_request(phone)
                return sent.phone_code_hash
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        else: db['staff_data'][phone]['status'] = "Online 🟢"
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
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    threading.Thread(target=run_loop, daemon=True).start()

# --- MAIN UI ---
db = load_db()

# Sidebar: Modern Dark Login
with st.sidebar:
    st.markdown("## 🛡️ Admin Portal")
    st.markdown("---")
    ph = st.text_input("Phone Number")
    nk = st.text_input("Nickname")
    
    if "h_hash" not in st.session_state:
        if st.button("🚀 Send OTP", use_container_width=True):
            res = asyncio.run(telegram_worker(ph, nk))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp = st.text_input("OTP Code")
        pw = st.text_input("2FA Password", type="password")
        if st.button("✅ Connect Account", use_container_width=True):
            f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
            if f is None:
                start_thread(ph, nk); st.success("Connected!"); del st.session_state.h_hash
            else: st.error(f)

# Top Section
st.markdown("<h1 style='text-align: center; color: #38bdf8;'>⭐ GUATEMALA TEAM PERFORMANCE ⭐</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #94a3b8;'>Real-time AI Monitoring & KPI Tracking System</p>", unsafe_allow_html=True)

# Metrics Cards
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 GLOBAL LEADS", len(db['global_customers']))
m2.metric("💰 TOTAL DEPOSITS", db['total_deposits'])
m3.metric("🔞 UNDER-AGE", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ REMOVED", db.get('total_deleted', 0))

st.markdown("---")

# Data Table & Individual Controls
col_data, col_actions = st.columns([2, 1])

with col_data:
    st.subheader("👨‍💼 Team Status")
    rows = []
    for p, s in db['staff_data'].items():
        l, d = len(s['customers']), len(s['depositors'])
        rows.append({
            "Staff": s['nickname'], "Leads": l, "Deposits": d,
            "U-Age": len(s.get('under_age', [])), "Conv%": f"{(d/l*100 if l>0 else 0):.1f}%"
        })
    if rows: st.table(pd.DataFrame(rows))
    else: st.info("Waiting for active connections...")

with col_actions:
    st.subheader("🛠️ Individual Actions")
    staff_list = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    
    target = st.selectbox("Select Account", list(staff_list.keys()) if staff_list else ["Empty"])
    
    btn1, btn2 = st.columns(2)
    if btn1.button("➖ Delete Lead", use_container_width=True):
        if staff_list and target != "Empty":
            p_t = staff_list[target]
            if db['staff_data'][p_t]['customers']:
                cid = db['staff_data'][p_t]['customers'].pop()
                if cid in db['global_customers']: db['global_customers'].remove(cid)
                db['total_deleted'] += 1; save_db(db); st.rerun()

    if btn2.button("📉 Deduct Dep", use_container_width=True):
        if staff_list and target != "Empty":
            p_t = staff_list[target]
            if db['staff_data'][p_t]['depositors']:
                db['staff_data'][p_t]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()

    st.markdown("---")
    # အကောင့်တစ်ခုချင်းစီ Logout လုပ်ရန် ခလုတ်
    if st.button("🚪 Logout Selected Account", type="primary", use_container_width=True):
        if staff_list and target != "Empty":
            p_t = staff_list[target]
            del db['staff_data'][p_t] # ရွေးထားတဲ့အကောင့်တစ်ခုတည်းကိုပဲ ဖျက်မယ်
            save_db(db)
            st.success(f"Logged out {target}")
            st.rerun()

    if st.button("🧹 Reset Stats Only", use_container_width=True):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']: db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()
