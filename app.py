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

# --- DATABASE LOGIC ---
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
        else:
            db['staff_data'][phone]['status'] = "Online 🟢"
        save_db(db)

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if event.is_private:
                db_now = load_db()
                u_id = event.sender_id
                if phone not in db_now['staff_data']: return

                # 1. Lead Update
                if u_id not in db_now['global_customers']: db_now['global_customers'].append(u_id)
                if u_id not in db_now['staff_data'][phone]['customers']:
                    db_now['staff_data'][phone]['customers'].append(u_id)

                # 2. Age Check
                msg = (event.message.message or "").lower()
                if any(x in msg for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)

                # 3. Receipt OCR Check
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

# --- STREAMLIT UI ---
st.set_page_config(page_title="Guatemala Pro Dashboard", layout="wide")
st_autorefresh(interval=5000, key="refresh")
db = load_db()

st.title("📊 Guatemala Team Pro Dashboard")

# --- SIDEBAR: LOGIN ---
with st.sidebar:
    st.header("🔐 Staff Login")
    ph = st.text_input("Phone Number")
    nk = st.text_input("Nickname")
    if "h_hash" not in st.session_state:
        if st.button("Send OTP"):
            res = asyncio.run(telegram_worker(ph, nk))
            if isinstance(res, str) and "Error" not in res:
                st.session_state.h_hash = res; st.success("OTP Sent!")
            else: st.error(res)
    else:
        otp = st.text_input("OTP Code")
        pw = st.text_input("2FA Password", type="password")
        if st.button("Connect"):
            f = asyncio.run(telegram_worker(ph, nk, otp, st.session_state.h_hash, pw))
            if f is None:
                start_thread(ph, nk); st.success("Connected!"); del st.session_state.h_hash
            else: st.error(f)

# --- MAIN METRICS ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Net Leads", len(db['global_customers']))
c2.metric("Verified Deposits", db['total_deposits'])
c3.metric("Under-age", sum(len(s.get('under_age', [])) for s in db['staff_data'].values()))
c4.metric("Total Deleted", db.get('total_deleted', 0))

st.markdown("---")

# --- PERFORMANCE TABLE ---
st.subheader("👨‍💼 Staff Performance")
rows = []
for p, s in db['staff_data'].items():
    l, d = len(s['customers']), len(s['depositors'])
    rows.append({"Staff": s['nickname'], "Phone": p, "Leads": l, "Deposits": d, "Conv%": f"{(d/l*100 if l>0 else 0):.1f}%"})
if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# --- ADMIN TOOLS (ကျန်နေခဲ့သော အပိုင်းများ) ---
st.markdown("---")
st.subheader("🛠 Admin Management")
col_tools, col_resets = st.columns(2)

with col_tools:
    st.write("**Account & Data Control**")
    staff_list = {f"{s['nickname']} ({p})": p for p, s in db['staff_data'].items()}
    
    with st.expander("🛡 Delete Lead / Deduct Deposit"):
        target_staff = st.selectbox("Select Staff", list(staff_list.keys()) if staff_list else ["None"], key="staff_sel")
        if st.button("Delete Last Lead") and staff_list:
            p_t = staff_list[target_staff]
            if db['staff_data'][p_t]['customers']:
                cid = db['staff_data'][p_t]['customers'].pop()
                if cid in db['global_customers']: db['global_customers'].remove(cid)
                db['total_deleted'] += 1; save_db(db); st.rerun()
        
        if st.button("Deduct 1 Deposit") and staff_list:
            p_t = staff_list[target_staff]
            if db['staff_data'][p_t]['depositors']:
                db['staff_data'][p_t]['depositors'].pop()
                db['total_deposits'] = max(0, db['total_deposits'] - 1)
                save_db(db); st.rerun()

    with st.expander("🚪 Logout / Remove Account"):
        to_logout = st.selectbox("Account to Remove", list(staff_list.keys()) if staff_list else ["None"], key="out_sel")
        if st.button("Logout Selected") and staff_list:
            p_t = staff_list[to_logout]
            del db['staff_data'][p_t]
            save_db(db); st.rerun()

with col_resets:
    st.write("**System Maintenance**")
    if st.button("🧹 Reset KPI Data Only", help="အကောင့်တွေမထွက်ဘဲ ဂဏန်းတွေပဲ သုညပြန်လုပ်မယ်"):
        db['global_customers'] = []; db['total_deleted'] = 0; db['total_deposits'] = 0
        for p in db['staff_data']:
            db['staff_data'][p].update({'customers': [], 'depositors': [], 'under_age': []})
        save_db(db); st.rerun()

    if st.button("🚫 Full System Reset", type="primary"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.rerun()
