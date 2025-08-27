# baileys_client.py
import os, requests
from urllib.parse import urlparse

_raw = os.getenv("BAILEYS_API_URL", "http://baileys-local-persist.railway.internal:3000").rstrip("/")
if not urlparse(_raw).scheme:
    _raw = "http://" + _raw
BASE = _raw  # ex.: http://baileys-local-persist.railway.internal:3000

def session_id(chat_id: int) -> str:
    return f"user_{chat_id}"

def get_status(chat_id: int, timeout: int = 8) -> dict:
    r = requests.get(f"{BASE}/status/{session_id(chat_id)}", timeout=timeout)
    r.raise_for_status()
    return r.json()

def get_qr(chat_id: int, timeout: int = 12) -> dict:
    r = requests.get(f"{BASE}/qr/{session_id(chat_id)}", timeout=timeout)
    r.raise_for_status()
    return r.json()

def send_message(chat_id: int, number: str, message: str, timeout: int = 20) -> dict:
    payload = {
        "session_id": session_id(chat_id),
        "number": number,
        "message": message
    }
    r = requests.post(f"{BASE}/send-message", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()
