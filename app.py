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

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Guatemala KPI Pro", page_icon="🌙", layout="wide")

# Deep Dark Theme Styling
st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .stTable { background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; }
    thead tr th { background-color: #334155 !important; color: #38bdf8 !important; }
    tbody tr td { color: #e2e8f0 !important; }
    .stButton>button { border-radius: 10px; background-color: #0ea5e9; color: white; border: none; transition: 0.3s; width: 100%; }
    .stButton>button:hover { background-color: #38bdf8; transform: translateY(-2px); }
    [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
    h1, h2, h3 { color: #38bdf8 !important; font-family: 'Inter', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- 2. DATA CONSTANTS ---
API_ID = 38792395
API_HASH = '4e8e3896fb5b1960993eec6a36c1b932'
DB_FILE = 'dashboard_data.json'
BANK_KEYWORDS = ["banrural", "industrial", "g&t", "azteca", "bac", "bantrab", "promerica", "bam", "transferencia", "monto", "exitoso", "comprobante"]

# --- 3. DATABASE LOGIC ---
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

# --- 4. TELEGRAM BACKGROUND WORKER ---
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
        
        # Add Staff if Authorized
        db = load_db()
        if phone not in db['staff_data']:
            db['staff_data'][phone] = {'nickname': nickname, 'customers': [], 'under_age': [], 'depositors': [], 'status': "Online 🟢"}
        save_db(db)

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return # Security check
                
                # Update Leads
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)
                
                # Update Age
                msg = (event.message.message or "").lower()
                if any(x in msg for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)
                
                # OCR for Deposits
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
    except: pass
    finally: await client.disconnect()

def start_thread(phone, nickname):
    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(telegram_worker(phone, nickname))
    threading.Thread(target=run_loop, daemon=True).start()

# --- 5. MAIN UI ---
db = load_db()

# Sidebar Login System
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.title("Admin Access")
    ph = st.text_input("Staff Phone", placeholder="+95...")
    nk = st.text_input("Staff Name", placeholder="E.g. Jhon")
    
    if "h_hash" not in st.session_state:
        if st.button("🚀 Send OTP Code"):
            res = asyncio.run(telegram_worker(ph, nk))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp = st.text_input("OTP Code")
        pw = st.text_input("2FA Password", type="password")
        if st.button("✅ Link Account"):
            f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
            if f is None:
                start_thread(ph, nk); st.success("Linked Successfully!"); del st.session_state.h_hash
            else: st.error(f)
    
    st.markdown("---")
    if st.button("💀 Critical System Reset", type="secondary"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()

# Main Header
st.markdown("<h1 style='text-align: center;'>🇬🇹 GUATEMALA PRO DASHBOARD</h1>", unsafe_allow_html=True)

# Metrics Grid
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 TOTAL LEADS", len(db['global_customers']))
m2.metric("💰 VERIFIED DEPOSITS", db['total_deposits'])
m3.metric("🔞 UNDER-AGE", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ REMOVED", db.get('total_deleted', 0))

st.markdown("---")

# Data Table & Management
col_left, col_right = st.columns([1.8, 1])

with col_left:
    st.subheader("👨‍💼 Team Performance")
    staff_rows = []
    for p, s in db['staff_data'].items():
        l, d = len(s['customers']), len(s['depositors'])
        staff_rows.append({
            "Staff": s['nickname'], "Phone": p, "Leads": l, 
            "Deps": d, "Conv%": f"{(d/l*100 if l>0 else 0):.1f}%"
        })
    if staff_rows: st.table(pd.DataFrame(staff_rows))
    else: st.info("No active staff monitored yet.")

with col_right:
    st.subheader("🛠️ Management Console")
    # Account Selector for Individual Actions
    staff_map = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    
    if staff_map:
        selected_key = st.selectbox("Choose Account", list(staff_map.keys()))
        target_phone = staff_map[selected_key]
        
        # Tools for individual
        c1, c2 = st.columns(2)
        if c1.button("➖ Delete Lead"):
            if db['staff_data'][target_phone]['customers']:
                cid = db['staff_data'][target_phone]['customers'].pop()
                if cid in db['global_customers']: db['global_customers'].remove(cid)
                db['total_deleted'] += 1; save_db(db); st.rerun()

        if c2.button("📉 Deduct Dep"):
            if db['staff_data'][target_phone]['depositors']:
                db['staff_data'][target_phone]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()

        st.markdown("---")
        # --- FIXED INDIVIDUAL LOGOUT ---
        if st.button("🚪 Logout Selected Account", type="primary"):
            if target_phone in db['staff_data']:
                del db['staff_data'][target_phone] # အဲ့ဒီတစ်ယောက်တည်းကိုပဲ database ကနေဖယ်မယ်
                save_db(db)
                st.success(f"Removed {selected_key}")
                st.rerun()

    else: st.write("No management options available.")

    if st.button("🧹 Clear Stats Only"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']: db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()
