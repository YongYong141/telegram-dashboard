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
import re

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

# --- 2. DATABASE & KEYWORDS ---
DB_FILE = 'dashboard_data.json'
API_ID = 38792395
API_HASH = '4e8e3896fb5b1960993eec6a36c1b932'
BANK_KEYWORDS = ["banrural", "industrial", "g&t", "azteca", "bac", "bantrab", "promerica", "bam", "transferencia", "monto", "exitoso", "comprobante", "boleta", "deposito", "efectivo"]

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

# --- 3. TELEGRAM CORE LOGIC (STABLE VERSION) ---
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
                    if password: await client.sign_in(password=password)
                    else: return "2FA_REQUIRED"
            else:
                sent = await client.send_code_request(phone)
                return sent.phone_code_hash
        
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {
                'nickname': nickname, 'customers': [], 
                'under_age_list': [], 'depositors': [], 
                'deleted_chats_count': 0, 'status': "Online 🟢"
            }
        save_db(db)

        # A. MESSAGE HANDLER (Leads, Under-age, OCR)
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return
                
                # 1. Update Global & Individual Leads
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)
                
                # 2. Under-Age Logic (15-19) - Regex for Accuracy
                msg_text = (event.message.message or "")
                if re.search(r'\b(15|16|17|18|19)\b', msg_text):
                    if u_id not in db_now['staff_data'][phone]['under_age_list']:
                        db_now['staff_data'][phone]['under_age_list'].append(u_id)

                # 3. Receipt OCR (Image Check)
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

        # B. AUTO-DELETE CHAT DETECTION (Every 2 mins)
        while True:
            await asyncio.sleep(120)
            db_chk = load_db()
            if phone in db_chk['staff_data']:
                active_list = db_chk['staff_data'][phone]['customers'][:]
                for cid in active_list:
                    try:
                        await client.get_input_entity(cid)
                    except:
                        # Chat deleted or blocked by customer
                        db_chk['staff_data'][phone]['customers'].remove(cid)
                        if cid in db_chk['global_customers']: db_chk['global_customers'].remove(cid)
                        
                        db_chk['staff_data'][phone]['deleted_chats_count'] += 1
                        db_chk['total_deleted'] += 1
                        
                        # Deduct deposit if they were a depositor
                        if cid in db_chk['staff_data'][phone]['depositors']:
                            db_chk['staff_data'][phone]['depositors'].remove(cid)
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

# --- 4. DASHBOARD UI ---
db = load_db()

with st.sidebar:
    st.title("🛡️ Admin Portal")
    ph_in = st.text_input("Phone (+95...)")
    nk_in = st.text_input("Staff Name")
    if "step" not in st.session_state: st.session_state.step = "GET_OTP"

    if st.session_state.step == "GET_OTP":
        if st.button("🚀 Send OTP Code"):
            res = asyncio.run(telegram_worker(ph_in, nk_in))
            if isinstance(res, str) and len(res) > 10:
                st.session_state.h_hash = res; st.session_state.step = "VERIFY"; st.rerun()
            else: st.error(f"Error: {res}")
    elif st.session_state.step == "VERIFY":
        otp_in = st.text_input("OTP Code")
        pwd_in = st.text_input("2FA Password (if any)", type="password")
        if st.button("✅ Link Account"):
            f = asyncio.run(telegram_worker(ph_in, nk_in, otp_in, st.session_state.h_hash, pwd_in))
            if f is None or f == "Online 🟢":
                start_thread(ph_in, nk_in); st.session_state.step = "GET_OTP"; st.rerun()
            elif f == "2FA_REQUIRED": st.warning("Please enter 2FA password.")
            else: st.error(f); st.session_state.step = "GET_OTP"

# GLOBAL METRICS
total_leads = len(db['global_customers'])
total_deps = db['total_deposits']
total_percent = (total_deps / total_leads * 100) if total_leads > 0 else 0
total_u_age = sum(len(s.get('under_age_list', [])) for s in db['staff_data'].values())

st.title("⭐ GUATEMALA PERFORMANCE MASTER ⭐")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("🌐 GLOBAL LEADS", total_leads)
m2.metric("💰 TOTAL DEPS", total_deps)
m3.metric("📊 TOTAL %", f"{total_percent:.1f}%")
m4.metric("🔞 TOTAL U-AGE", total_u_age)
m5.metric("🗑️ AUTO REMOVED", db.get('total_deleted', 0))

st.markdown("---")

# PERFORMANCE TABLE
st.subheader("👨‍💼 Staff Performance Detailed View")
rows = []
for p, s in db['staff_data'].items():
    l, d = len(s['customers']), len(s['depositors'])
    u_a = len(s.get('under_age_list', []))
    del_c = s.get('deleted_chats_count', 0)
    rows.append({
        "Staff": s['nickname'], "Leads": l, "Depositors": d,
        "Under-Age": u_a, "Deleted Chat": del_c,
        "Conv %": f"{(d/l*100 if l>0 else 0):.1f}%"
    })
if rows: st.table(pd.DataFrame(rows))
else: st.info("No active staff accounts.")

# MANAGEMENT TOOLS
st.subheader("🛠️ Management Console")
staff_map = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
if staff_map:
    sel = st.selectbox("Select Account", list(staff_map.keys()))
    target_ph = staff_map[sel]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("➖ Manual Lead Deduct"):
            if db['staff_data'][target_ph]['customers']:
                db['staff_data'][target_ph]['customers'].pop()
                if db['global_customers']: db['global_customers'].pop()
                save_db(db); st.rerun()
    with col2:
        if st.button("📉 Manual Dep Deduct"):
            if db['staff_data'][target_ph]['depositors']:
                db['staff_data'][target_ph]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()
    with col3:
        if st.button("🚪 Logout Account", type="primary"):
            del db['staff_data'][target_ph]; save_db(db); st.rerun()

st.markdown("---")
if st.button("🧹 Global Reset (All Data)"):
    db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
    for p in db['staff_data']: 
        db['staff_data'][p].update({'customers': [], 'under_age_list': [], 'depositors': [], 'deleted_chats_count': 0})
    save_db(db); st.rerun()
