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
import easyocr # Cloud ပေါ်မှာ အဆင်ပြေပြေစာဖတ်နိုင်တဲ့ Library
import numpy as np

# --- CONFIGURATION ---
API_ID = 38792395
API_HASH = '4e8e3896fb5b1960993eec6a36c1b932'
DB_FILE = 'dashboard_data.json'

# Guatemala Banks Keywords
BANK_KEYWORDS = ["banrural", "industrial", "g&t", "azteca", "bac", "bantrab", "promerica", "bam", "transferencia", "monto", "exitoso", "comprobante"]

# Initialize EasyOCR
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['es', 'en']) # စပိန်ဘာသာနဲ့ အင်္ဂလိပ်ဘာသာကို ဖတ်မယ်

reader = load_ocr()

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

                msg_text = (event.message.message or "").lower()
                if any(x in msg_text for x in ["15","16","17","18","19"]):
                    if u_id not in db_now['staff_data'][phone]['under_age']:
                        db_now['staff_data'][phone]['under_age'].append(u_id)

                if event.photo:
                    try:
                        photo_bytes = await event.download_media(file=bytes)
                        img_array = np.array(Image.open(io.BytesIO(photo_bytes)))
                        result = reader.readtext(img_array, detail=0)
                        extracted = " ".join(result).lower()
                        
                        if any(key in extracted for key in BANK_KEYWORDS):
                            if u_id not in db_now['staff_data'][phone]['depositors']:
                                db_now['staff_data'][phone]['depositors'].append(u_id)
                                db_now['total_deposits'] += 1
                    except: pass
                
                save_db(db_now)
        await client.run_until_disconnected()
    except Exception as e: return str(e)
    finally: await client.disconnect()

# --- STREAMLIT UI (PC Version အတိုင်း အကုန်ပြန်ပါသည်) ---
# ... (အရင်က ပေးထားတဲ့ UI code အကုန်လုံးကို ဒီမှာ ပြန်သုံးနိုင်ပါတယ်)