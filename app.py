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
st.set_page_config(page_title="KPI Dark Dashboard", page_icon="🌙", layout="wide")

# CSS for Dark Theme
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
    .stButton>button { border-radius: 10px; background-color: #0ea5e9; color: white; border: none; transition: 0.3s; width: 100%; height: 45px; font-weight: bold; }
    .stButton>button:hover { background-color: #38bdf8; transform: translateY(-2px); }
    [data-testid="stSidebar"] { background-color: #020617 !important; border-right: 1px solid #1e293b; }
    h1, h2, h3 { color: #38bdf8 !important; }
    </style>
    """, unsafe_allow_html=True)

st_autorefresh(interval=5000, key="refresh")

# --- 2. DATA CONFIG ---
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
                
                # Update Leads
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)
                
                # Update Age (15-19)
                msg = (event.message.message or "").lower()
                if any(x in msg for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)
                
                # OCR Check for Deposits
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

# --- 5. DASHBOARD MAIN UI ---
db = load_db()

with st.sidebar:
    st.title("🛡️ Admin Portal")
    ph_input = st.text_input("Phone Number")
    nk_input = st.text_input("Nickname")
    
    if "h_hash" not in st.session_state:
        if st.button("🚀 Send OTP"):
            res = asyncio.run(telegram_worker(ph_input, nk_input))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp_in = st.text_input("OTP Code")
        pw_in = st.text_input("2FA Password", type="password")
        if st.button("✅ Link Account"):
            f = asyncio.run(telegram_worker(ph_input, nk_input, otp_in, st.session_state.h_hash, pw_in))
            if f is None:
                start_thread(ph_input, nk_input); st.success("Connected!"); del st.session_state.h_hash
            else: st.error(f)
    
    st.markdown("---")
    if st.button("🚫 Full System Reset"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()

st.markdown("<h1 style='text-align: center;'>🇬🇹 GUATEMALA PERFORMANCE (DARK MODE)</h1>", unsafe_allow_html=True)

# Main Stats
m1, m2, m3, m4 = st.columns(4)
m1.metric("🌐 GLOBAL LEADS", len(db['global_customers']))
m2.metric("💰 TOTAL DEPOSITS", db['total_deposits'])
m3.metric("🔞 UNDER-AGE", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
m4.metric("🗑️ REMOVED", db.get('total_deleted', 0))

st.markdown("---")

col_left, col_right = st.columns([1.5, 1])

with col_left:
    st.subheader("👨‍💼 Staff Productivity")
    rows = []
    for p, s in db['staff_data'].items():
        l, d = len(s['customers']), len(s['depositors'])
        rows.append({
            "Staff": s['nickname'], "Phone": p, "Leads": l, 
            "Deps": d, "U-Age": len(s.get('under_age', [])), 
            "Status": s.get('status', 'Offline')
        })
    if rows: st.table(pd.DataFrame(rows))
    else: st.info("No active accounts found.")

with col_right:
    st.subheader("🛠️ Management Console")
    # ဝန်ထမ်းရွေးချယ်ရန် Selector
    staff_options = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    
    if staff_options:
        selected_account = st.selectbox("Select Account to Manage", list(staff_options.keys()))
        target_p = staff_options[selected_account]
        
        st.write(f"Actions for: **{selected_account}**")
        
        # ၁။ တစ်ယောက်ချင်း Leads လျော့တာ
        if st.button("➖ Delete Last Lead from this Account"):
            if db['staff_data'][target_p]['customers']:
                last_cid = db['staff_data'][target_p]['customers'].pop()
                if last_cid in db['global_customers']: db['global_customers'].remove(last_cid)
                db['total_deleted'] += 1
                save_db(db); st.rerun()

        # ၂။ တစ်ယောက်ချင်း Deposit လျော့တာ
        if st.button("📉 Deduct 1 Deposit from this Account"):
            if db['staff_data'][target_p]['depositors']:
                db['staff_data'][target_p]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()

        st.markdown("---")
        # ၃။ တစ်ယောက်ချင်း Logout လုပ်တာ
        if st.button("🚪 Logout Selected Account Only", type="primary"):
            if target_p in db['staff_data']:
                del db['staff_data'][target_p]
                save_db(db)
                st.success(f"Removed {selected_account}")
                st.rerun()
    else:
        st.write("Connect an account to see management tools.")

    if st.button("🧹 Reset All Numbers (Keep Accounts)"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']:
            db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()
