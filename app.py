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

# --- PAGE SETUP ---
st.set_page_config(page_title="KPI Performance Dashboard", layout="wide")

# Custom CSS for Modern Design
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 5px solid #007bff;
    }
    .stDataFrame { border-radius: 10px; }
    h1 { color: #1e3a8a; font-family: 'Helvetica', sans-serif; }
    .status-online { color: #10b981; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- DATABASE LOGIC (NO CHANGES) ---
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

# --- TELEGRAM WORKER (NO CHANGES) ---
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
        else:
            db['staff_data'][phone]['status'] = "Online 🟢"
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

# Sidebar Design
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
    st.title("Admin Portal")
    st.markdown("---")
    st.subheader("🔐 Staff Connection")
    ph = st.text_input("Phone Number", placeholder="+95...")
    nk = st.text_input("Staff Nickname", placeholder="Name")
    
    if "h_hash" not in st.session_state:
        if st.button("Get OTP Code", use_container_width=True):
            res = asyncio.run(telegram_worker(ph, nk))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp = st.text_input("Enter 5-digit OTP")
        pw = st.text_input("2FA Password (If any)", type="password")
        if st.button("Authorize & Connect", use_container_width=True, type="primary"):
            f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
            if f is None:
                start_thread(ph, nk); st.success("Connected!"); del st.session_state.h_hash
            else: st.error(f)

# Header Section
st.title("📈 Performance Analytics")
st.markdown(f"**Last Sync:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Top Metrics with Design
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 Total Net Leads", len(db['global_customers']), delta="Real-time")
m2.metric("💰 Verified Deposits", db['total_deposits'], delta="By OCR", delta_color="normal")
m3.metric("🔞 Under-age (15-19)", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ Total Deleted", db.get('total_deleted', 0))

st.markdown("---")

# Data Presentation Table
st.subheader("👨‍💼 Active Team Performance")
rows = []
for p, s in db['staff_data'].items():
    l, d = len(s['customers']), len(s['depositors'])
    rows.append({
        "Staff Name": s['nickname'],
        "Telegram ID": p,
        "Leads": l,
        "Deposits": d,
        "U-Age": len(s.get('under_age', [])),
        "Conversion": f"{(d/l*100 if l>0 else 0):.1f}%",
        "Status": "🟢 Active"
    })

if rows:
    df = pd.DataFrame(rows)
    st.table(df) # table ပုံစံက ပိုပြီး ရှင်းလင်းတည်ငြိမ်ပါတယ်
else:
    st.info("No active staff connected yet.")

# Admin Tools Section
st.markdown("---")
st.subheader("🛠️ Management Tools")
t1, t2 = st.columns(2)

with t1:
    with st.expander("📝 Manual Adjustments"):
        staff_list = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
        target = st.selectbox("Select Staff Account", list(staff_list.keys()) if staff_list else ["None"])
        
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("➖ Delete Last Lead", use_container_width=True):
            if staff_list:
                p_t = staff_list[target]
                if db['staff_data'][p_t]['customers']:
                    cid = db['staff_data'][p_t]['customers'].pop()
                    if cid in db['global_customers']: db['global_customers'].remove(cid)
                    db['total_deleted'] += 1; save_db(db); st.rerun()
                    
        if btn_col2.button("📉 Deduct 1 Deposit", use_container_width=True):
            if staff_list:
                p_t = staff_list[target]
                if db['staff_data'][p_t]['depositors']:
                    db['staff_data'][p_t]['depositors'].pop()
                    db['total_deposits'] = max(0, db['total_deposits'] - 1)
                    save_db(db); st.rerun()

with t2:
    with st.expander("⚙️ System Control"):
        if st.button("🧹 Clear KPI Data (Keep Accounts)", use_container_width=True):
            db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
            for p in db['staff_data']:
                db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
            save_db(db); st.rerun()
            
        if st.button("🚪 Logout Selected Account", use_container_width=True):
            if staff_list:
                p_t = staff_list[target]
                del db['staff_data'][p_t]
                save_db(db); st.rerun()

# Full Reset in Sidebar for safety
if st.sidebar.button("⚠️ Full System Reset", type="secondary"):
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    st.rerun()
