import json
import os
import re
import threading
import time

from google import genai
from google.genai import types

from . import config

_client = None
_lock = threading.Lock()
status = {"state": "idle", "error": "", "device": "Gemini API", "model": config.MODEL_ID}
FATAL = ("API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED", "403", "NOT_FOUND", "404")
RETRY = ("429", "500", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED")


def load():
    global _client
    with _lock:
        if _client is not None:
            return _client
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            msg = "No API key found. Put GEMINI_API_KEY=... in a .env file next to run.py."
            status.update(state="error", error=msg)
            raise RuntimeError(msg)
        _client = genai.Client(api_key=key)
        status.update(state="ready", error="")
        return _client


def chat(system, user, max_new_tokens=None):
    client = load()
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0,
        max_output_tokens=max_new_tokens or config.MAX_NEW_TOKENS,
    )
    for attempt in range(6):
        try:
            r = client.models.generate_content(model=config.MODEL_ID, contents=user, config=cfg)
            return (r.text or "").strip()
        except Exception as e:
            msg = str(e)
            if any(f in msg for f in FATAL):
                status.update(state="error", error=msg[:300])
                raise
            if attempt == 5 or not any(r in msg for r in RETRY):
                raise
            time.sleep(min(2 ** attempt * 3, 60))


def parse_json(raw):
    dec = json.JSONDecoder()
    best = None
    for m in re.finditer(r"[{\[]", raw):
        try:
            obj, end = dec.raw_decode(raw[m.start():])
        except ValueError:
            continue
        if best is None or end > best[0]:
            best = (end, obj)
    if best:
        return best[1]
    start = raw.find("{")
    if start < 0:
        return None
    cut = raw[start:]
    for _ in range(6):
        idx = cut.rfind("},")
        if idx < 0:
            break
        cut = cut[: idx + 1]
        try:
            return json.loads(cut + "]}")
        except ValueError:
            continue
    return None


def chat_json(system, user, retries=1):
    for _ in range(retries + 1):
        data = parse_json(chat(system, user))
        if data is not None:
            return data
        user += "\n\nYour previous reply was not valid JSON. Reply with one valid JSON object only."
    return None


def preload():
    try:
        load()
    except Exception:
        pass
