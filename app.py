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

# --- PAGE CONFIG ---
st.set_page_config(page_title="Guatemala KPI Pro", page_icon="🇬🇹", layout="wide")

# Modern Styling
st.markdown("""
    <style>
    /* Main Background */
    .stApp { background-color: #f8fafc; }
    
    /* Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 15px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
    }
    
    /* Table Styling */
    .stTable {
        background-color: white;
        border-radius: 12px;
        overflow: hidden;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #1e293b;
        color: white;
    }
    section[data-testid="stSidebar"] .stMarkdown h1, h2, h3 { color: white; }

    /* Button Styling */
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s;
    }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- DATABASE (NO CHANGES) ---
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

# --- TELEGRAM LOGIC (NO CHANGES) ---
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

# --- MAIN DASHBOARD ---
db = load_db()

# SIDEBAR: Modern Login UI
with st.sidebar:
    st.title("🛡️ Admin Panel")
    st.markdown("---")
    with st.container():
        st.subheader("Connect Staff")
        ph = st.text_input("Phone Number", placeholder="+95...")
        nk = st.text_input("Nickname", placeholder="Staff Name")
        
        if "h_hash" not in st.session_state:
            if st.button("🚀 Get OTP", use_container_width=True):
                res = asyncio.run(telegram_worker(ph, nk))
                if isinstance(res, str) and "Error" not in res:
                    st.session_state.h_hash = res; st.success("OTP Sent!")
                else: st.error(res)
        else:
            otp = st.text_input("Enter OTP Code")
            pw = st.text_input("2FA Password", type="password")
            if st.button("✅ Connect Account", use_container_width=True, type="primary"):
                f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
                if f is None:
                    start_thread(ph, nk); st.success("Connected!"); del st.session_state.h_hash
                else: st.error(f)
    
    st.markdown("---")
    if st.button("⚠️ Full System Reset", type="secondary", use_container_width=True):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()

# TOP HEADER
st.title("🇬🇹 Guatemala Performance Dashboard")
st.markdown("Monitoring your team's real-time productivity and verified deposits.")

# METRIC CARDS
c1, c2, c3, c4 = st.columns(4)
c1.metric("🌐 Total Net Leads", len(db['global_customers']))
c2.metric("💰 Verified Deposits", db['total_deposits'])
c3.metric("🔞 Under-age (15-19)", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
c4.metric("🗑️ Total Deleted", db.get('total_deleted', 0))

st.markdown("---")

# PERFORMANCE TABLE Section
col_table, col_tools = st.columns([2, 1])

with col_table:
    st.subheader("👨‍💼 Team Status")
    rows = []
    for p, s in db['staff_data'].items():
        l, d = len(s['customers']), len(s['depositors'])
        rows.append({
            "Staff": s['nickname'],
            "Leads": l,
            "Deposits": d,
            "U-Age": len(s.get('under_age', [])),
            "Conv %": f"{(d/l*100 if l>0 else 0):.1f}%"
        })
    if rows:
        st.table(pd.DataFrame(rows))
    else:
        st.info("Waiting for staff connections...")

with col_tools:
    st.subheader("🛠️ Quick Actions")
    staff_list = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    
    with st.expander("Adjustment Tools"):
        target = st.selectbox("Select Account", list(staff_list.keys()) if staff_list else ["None"])
        if st.button("Delete Last Lead", use_container_width=True):
            if staff_list:
                p_t = staff_list[target]
                if db['staff_data'][p_t]['customers']:
                    cid = db['staff_data'][p_t]['customers'].pop()
                    if cid in db['global_customers']: db['global_customers'].remove(cid)
                    db['total_deleted'] += 1; save_db(db); st.rerun()
                    
        if st.button("Deduct 1 Deposit", use_container_width=True):
            if staff_list:
                p_t = staff_list[target]
                if db['staff_data'][p_t]['depositors']:
                    db['staff_data'][p_t]['depositors'].pop()
                    db['total_deposits'] = max(0, db['total_deposits'] - 1)
                    save_db(db); st.rerun()

    if st.button("🧹 Reset All Numbers", use_container_width=True):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']:
            db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()

    if st.button("🚪 Logout Selected", use_container_width=True):
        if staff_list:
            del db['staff_data'][staff_list[target]]
            save_db(db); st.rerun()
