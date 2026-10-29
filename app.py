import datetime
import html
import json
import logging
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from pypdf import PdfReader

# Silence harmless pypdf fontTools warnings in the terminal
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Lock Streamlit to Light Mode so nothing is ever blacked out
os.makedirs(".streamlit", exist_ok=True)
config_path = os.path.join(".streamlit", "config.toml")
if not os.path.exists(config_path):
    with open(config_path, "w", encoding="utf-8") as f:
        f.write('[theme]\nbase = "light"\nprimaryColor = "#0066EE"\nbackgroundColor = "#F7F8FA"\nsecondaryBackgroundColor = "#FFFFFF"\ntextColor = "#111827"\n')

load_dotenv()
DB_FILE = "mediclear_history.db"

st.set_page_config(
    page_title="MediClear — Lab Translator & Streak Tracker",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Database setup and helper functions
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS saved_reports ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, doc_name TEXT, saved_at TEXT, "
        "raw_text TEXT, report_json TEXT, streak_json TEXT)"
    )
    conn.commit()
    conn.close()


def normalize_streak_dates(raw_streak):
    today = datetime.date.today()
    if not isinstance(raw_streak, list):
        return []
    if all(isinstance(x, str) for x in raw_streak):
        return sorted(list(set(raw_streak)))
    dates = []
    for i, val in enumerate(raw_streak[:7]):
        if val is True:
            d = today - datetime.timedelta(days=(6 - i))
            dates.append(d.isoformat())
    return sorted(list(set(dates)))


def save_report(doc_name, raw_text, report_data, streak_dates):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    cur.execute(
        "INSERT INTO saved_reports (doc_name, saved_at, raw_text, report_json, streak_json) VALUES (?, ?, ?, ?, ?)",
        (doc_name, now_str, raw_text, json.dumps(report_data), json.dumps(streak_dates)),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_streak(report_id, streak_dates):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE saved_reports SET streak_json = ? WHERE id = ?", (json.dumps(sorted(list(set(streak_dates)))), report_id))
    conn.commit()
    conn.close()


def get_history():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT id, doc_name, saved_at, raw_text, report_json, streak_json FROM saved_reports ORDER BY id DESC").fetchall()
    conn.close()
    items = []
    for r in rows:
        dates = normalize_streak_dates(json.loads(r[5]))
        items.append({"id": r[0], "doc_name": r[1], "saved_at": r[2], "raw_text": r[3], "report_json": json.loads(r[4]), "streak_dates": dates})
    return items


def delete_report(report_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM saved_reports WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()


def wipe_all_history():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM saved_reports")
    conn.commit()
    conn.close()


# Page styling
def load_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        :root, html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
            color-scheme: light !important;
            --primary-color: #0066EE !important;
            --background-color: #F7F8FA !important;
            --secondary-background-color: #FFFFFF !important;
            --text-color: #111827 !important;
            background-color: #F7F8FA !important;
            color: #111827 !important;
            font-family: 'Inter', sans-serif !important;
        }
        #MainMenu, footer {visibility: hidden;}
        header {background: transparent !important;}
        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #EAECEF !important;
        }
        label, p, span, div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stRadio"] label, div[data-testid="stCheckbox"] label {
            color: #111827 !important;
        }
        input, textarea,
        [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
        div[data-baseweb="input"] > div, div[data-baseweb="base-input"] > div,
        div[data-baseweb="textarea"] > div, div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] div, [data-testid="stDateInput"] input {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            border-color: #D1D5DB !important;
            caret-color: #111827 !important;
        }
        input::placeholder, textarea::placeholder {
            color: #9CA3AF !important;
            -webkit-text-fill-color: #9CA3AF !important;
        }
        [data-baseweb="popover"], [data-baseweb="popover"] *,
        [data-baseweb="calendar"], [data-baseweb="calendar"] *,
        [data-baseweb="datepicker"], [data-baseweb="datepicker"] *,
        [data-baseweb="menu"], [data-baseweb="menu"] *,
        [role="listbox"], [role="listbox"] *,
        [role="dialog"], [role="dialog"] *,
        [role="application"], [role="application"] *,
        [role="grid"], [role="grid"] *,
        [role="tooltip"], [role="tooltip"] *,
        [data-baseweb="tooltip"], [data-baseweb="tooltip"] *,
        [data-testid="stTooltipContent"] {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border-color: #E5E7EB !important;
        }
        [role="gridcell"]:hover, [role="gridcell"]:hover *,
        [role="option"]:hover, [role="option"]:hover * {
            background-color: #EFF6FF !important;
            color: #0066EE !important;
        }
        [data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section {
            background-color: #F9FAFB !important;
            color: #111827 !important;
            border: 2px dashed #CBD5E1 !important;
            border-radius: 14px !important;
        }
        [data-testid="stFileUploaderDropzone"] button {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border: 1px solid #D1D5DB !important;
            border-radius: 999px !important;
        }
        [data-testid="stExpander"], [data-testid="stExpander"] details, [data-testid="stExpander"] summary {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border-radius: 14px !important;
        }
        pre, code, [data-testid="stCodeBlock"], [data-testid="stCode"] {
            background-color: #F8FAFC !important;
            color: #111827 !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 12px !important;
        }
        .block-container { max-width: 1160px !important; padding-top: 1.2rem !important; padding-bottom: 3rem !important; }
        .card { background: #FFFFFF; border: 1px solid #EAECEF; border-radius: 20px; padding: 22px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); margin-bottom: 16px; }
        .card-sm { background: #FFFFFF; border: 1px solid #EAECEF; border-radius: 16px; padding: 15px 18px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); margin-bottom: 12px; }
        .pill { display: inline-block; border-radius: 999px; padding: 4px 12px; font-weight: 600; font-size: 12px; white-space: nowrap; }
        .pill-red { background: #FEF2F2; color: #DC2626 !important; border: 1px solid #FECACA; }
        .pill-green { background: #ECFDF5; color: #059669 !important; border: 1px solid #A7F3D0; }
        .pill-blue { background: #EFF6FF; color: #0066EE !important; border: 1px solid #BFDBFE; }
        .section-tag { background: #0066EE; color: #FFFFFF !important; border-radius: 999px; padding: 5px 13px; font-size: 12px; font-weight: 700; text-transform: uppercase; }
        .track { position: relative; height: 10px; background: #F3F4F6; border-radius: 999px; margin: 12px 0 8px 0; }
        .zone { position: absolute; top: 0; height: 10px; background: rgba(16,185,129,0.28); border: 1px solid #10B981; border-radius: 999px; }
        .pin { position: absolute; top: -4px; width: 18px; height: 18px; border-radius: 50%; border: 3px solid #FFFFFF; box-shadow: 0 2px 6px rgba(0,0,0,0.22); transform: translateX(-50%); }
        .swap-row { display: grid; grid-template-columns: 1fr 30px 1fr; align-items: center; gap: 10px; margin-top: 8px; }
        .box-bad { background: #FEF2F2; border: 1px solid #FEE2E2; border-radius: 14px; padding: 12px; }
        .box-good { background: #ECFDF5; border: 1px solid #D1FAE5; border-radius: 14px; padding: 12px; }
        .day-box { border-radius: 14px; padding: 10px 4px; text-align: center; margin-bottom: 6px; }
        .day-on { background: #FFF4ED; border: 2px solid #FC4C02; color: #FC4C02 !important; font-weight: 800; }
        .day-off { background: #F9FAFB; border: 1px solid #EAECEF; color: #6B7280 !important; font-weight: 600; }
        button, .stButton > button, .stDownloadButton > button,
        [data-testid="stSidebar"] button, div[data-baseweb="input"] button, div[data-baseweb="base-input"] button {
            background-color: #FFFFFF !important;
            color: #111827 !important;
            border: 1px solid #D1D5DB !important;
            border-radius: 999px !important;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] button svg, div[data-baseweb="input"] button svg, div[data-baseweb="base-input"] button svg {
            fill: #111827 !important;
            color: #111827 !important;
        }
        button:hover, .stButton > button:hover, .stDownloadButton > button:hover {
            border-color: #0066EE !important;
            color: #0066EE !important;
            background-color: #EFF6FF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# PDF reader, Gemini API caller with 503 retry, and MP3 voice generator
def read_pdf(uploaded_file):
    if uploaded_file.name.lower().endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")
    reader = PdfReader(uploaded_file)
    return "\n".join([page.extract_text() or "" for page in reader.pages]).strip()


def call_gemini(prompt, api_key):
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    available_models = []
    try:
        with urllib.request.urlopen(list_url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                name = m.get("name", "")
                if "generateContent" in methods and "gemini" in name.lower():
                    available_models.append(name)
    except Exception as e:
        raise RuntimeError(f"Could not verify Gemini API key ({e}).")

    # Prioritize stable production models first so we avoid overloaded preview models
    preferred_order = [
        "models/gemini-2.5-flash-lite",
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-lite",
        "models/gemini-flash-latest",
        "models/gemini-pro-latest",
    ]
    ordered_models = [m for m in preferred_order if m in available_models]
    for m in available_models:
        if m not in ordered_models and "tts" not in m.lower() and "image" not in m.lower():
            ordered_models.append(m)

    last_err = ""
    for model_path in ordered_models[:8]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent?key={api_key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }).encode("utf-8")
        for attempt in range(2):
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as he:
                last_err = f"HTTP {he.code}: {he.reason}"
                if he.code in (429, 503) and attempt == 0:
                    time.sleep(1.2)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                break

    raise RuntimeError(f"Gemini API error: {last_err}")


def fallback_local_parser(report_text):
    # Failsafe local parser in case Google's Gemini servers are down (503)
    patterns = [
        ("Cholesterol, Total", r"Cholesterol,\s*Total\s+(\d+(?:\.\d+)?)", "mg/dL", 100.0, 199.0, "Measures total blood cholesterol.", "Keeping total cholesterol balanced protects your arteries.", "Fried foods and fatty cuts of red meat", "Oats, beans, and high fiber foods", "Sitting for long hours", "Taking a brisk 30 minute walk daily"),
        ("Triglycerides", r"Triglycerides\s+(\d+(?:\.\d+)?)", "mg/dL", 0.0, 149.0, "Measures circulating blood fats.", "High triglycerides can affect heart health and metabolism.", "Sugary drinks, pastries, and white bread", "Salmon, walnuts, and high fiber greens", "Skipping regular exercise", "20 minutes of brisk walking or cycling after meals"),
        ("HDL Cholesterol", r"HDL\s+Cholesterol\s+(\d+(?:\.\d+)?)", "mg/dL", 39.0, 100.0, "Your good cholesterol that clears extra fat from blood vessels.", "Higher good cholesterol helps protect your heart.", "Processed trans fats", "Olive oil, avocado, and nuts", "Sedentary routine", "Regular aerobic exercise"),
        ("VLDL Cholesterol Cal", r"VLDL\s+Cholesterol(?:\s+Cal)?\s+(\d+(?:\.\d+)?)", "mg/dL", 5.0, 40.0, "Measures a carrier fat particle in your blood.", "Keeping VLDL in range reduces fat buildup in arteries.", "Refined sugars", "Whole grains and vegetables", "Inactive evenings", "Daily evening walk"),
        ("LDL Chol Calc (NIH)", r"LDL\s+Chol(?:esterol)?(?:\s+Calc\s*\(NIH\))?\s+(\d+(?:\.\d+)?)", "mg/dL", 0.0, 99.0, "Your bad cholesterol that can build up in arteries.", "Keeping LDL under 100 mg/dL keeps blood vessels clear.", "Butter, full fat cheese, and cream sauces", "Avocados, olive oil, oats, and almonds", "Skipping weekly cardio", "30 minutes of brisk walking or jogging"),
        ("Glucose", r"Glucose\s+(\d+(?:\.\d+)?)", "mg/dL", 65.0, 99.0, "Measures your fasting blood sugar level.", "Healthy blood sugar protects blood vessels and energy.", "Sugary sodas and white bread", "Water with lemon and fiber rich whole grains", "Sitting right after meals", "15 minute walk after eating"),
        ("Hemoglobin A1c", r"Hemoglobin\s+A1c\s+(\d+(?:\.\d+)?)", "%", 4.5, 5.6, "Measures your 3 month average blood sugar.", "Helps track long term blood sugar control.", "Refined carbs and sweets", "Steel cut oats, beans, and greens", "Irregular meal times", "Consistent meal schedule and post meal walks"),
    ]
    labs = []
    for name, pat, unit, low, high, mean, why, f_bad, f_good, h_bad, h_good in patterns:
        matches = re.findall(pat, report_text, flags=re.IGNORECASE)
        if matches:
            val = float(matches[-1])
            labs.append({
                "name": name, "value": val, "unit": unit, "low_limit": low, "high_limit": high,
                "meaning": mean, "why_important": why, "food_instead": f_bad, "food_try": f_good,
                "habit_instead": h_bad, "habit_try": h_good,
                "keep_doing": f"Continue eating whole foods ({f_good.lower()}) and staying active.",
            })
    return {
        "summary": "Your lab report has been analyzed. Review your markers on the left and follow the personalized food and movement swaps below for any elevated values.",
        "labs": labs,
    }


def analyze_report(report_text, api_key):
    prompt = f"""
You are a clinical lab translator. Read ONLY the user's medical report below. Do NOT invent lab results that are not in the text.
If a reference range is not explicitly printed next to a lab marker, use standard adult clinical reference limits.
For each lab marker:
- Provide 1 Food Swap (food_instead -> food_try) and 1 Movement or Lifestyle Habit (habit_instead -> habit_try).
- Also provide "keep_doing": a 1-sentence tip on what healthy food or activity habit to continue if this marker is already Optimal.
Return ONLY valid JSON with this exact structure:
{{
  "summary": "Warm, easy-to-read 5th-grade plain-English summary of what this report says (2-4 sentences).",
  "labs": [
    {{
      "name": "Lab Marker Name",
      "value": 115.0,
      "unit": "mg/dL",
      "low_limit": 65.0,
      "high_limit": 99.0,
      "meaning": "Simple 5th-grade explanation of what this specific number means for the patient's body.",
      "why_important": "1 sentence on why this marker matters for health.",
      "food_instead": "Specific food to reduce/avoid",
      "food_try": "Specific whole-food swap to improve this marker",
      "habit_instead": "Specific sedentary or lifestyle habit to avoid",
      "habit_try": "Specific physical movement or daily habit to improve this marker",
      "keep_doing": "What healthy food & activity habit to continue doing to keep this number in the healthy range"
    }}
  ]
}}

USER REPORT TEXT:
{report_text}
"""
    try:
        raw = call_gemini(prompt, api_key)
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        s, e = cleaned.find("{"), cleaned.rfind("}")
        return json.loads(cleaned[s : e + 1] if (s != -1 and e != -1) else cleaned)
    except Exception as api_err:
        fallback = fallback_local_parser(report_text)
        if fallback["labs"]:
            return fallback
        raise api_err


def generate_speech_mp3(text):
    words = text.split()
    chunks, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= 180:
            cur = f"{cur} {w}".strip()
        else:
            chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)

    audio_bytes = b""
    for chunk in chunks:
        q = urllib.parse.quote(chunk)
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            audio_bytes += resp.read()
    return audio_bytes


# Reference range math and clinical equations
def calc_math(val, low, high):
    midpoint = (low + high) / 2.0
    if val > high:
        status, direction = "High", "Above Upper Limit"
        dev_pct = ((val - high) / high) * 100.0 if high > 0 else (val - high) * 100.0
        gap, target_bound = val - high, high
    elif val < low:
        status, direction = "Low", "Below Lower Limit"
        dev_pct = ((low - val) / low) * 100.0 if low > 0 else (low - val) * 100.0
        gap, target_bound = low - val, low
    else:
        status, direction = "Optimal", "Within Normal Range"
        dev_pct, gap, target_bound = 0.0, 0.0, val

    return {
        "status": status, "dev_pct": round(dev_pct, 2), "midpoint": round(midpoint, 2),
        "gap": round(gap, 2), "target_bound": round(target_bound, 2), "direction": direction,
        "scale_max": round(max(high * 1.5, val * 1.25, 1.0), 2),
    }


def get_clinical_equations(labs):
    lookup = {item["name"].lower(): float(item["value"]) for item in labs}
    results = []
    for k, val in lookup.items():
        if "a1c" in k:
            results.append({"name": "Estimated Average Glucose (eAG)", "value": f"{(28.7 * val) - 46.7:.1f} mg/dL", "formula": f"ADAG Formula: (28.7 × {val:g}) − 46.7"})
            break
    ldl = next((v for k, v in lookup.items() if "ldl" in k), None)
    hdl = next((v for k, v in lookup.items() if "hdl" in k), None)
    tg = next((v for k, v in lookup.items() if "triglyceride" in k or k == "tg"), None)
    if ldl and hdl and hdl > 0:
        results.append({"name": "LDL-to-HDL Ratio", "value": f"{ldl / hdl:.2f}", "formula": f"LDL ({ldl:g}) ÷ HDL ({hdl:g}) [Target < 2.5]"})
    if tg and hdl and hdl > 0:
        results.append({"name": "Triglyceride-to-HDL Ratio", "value": f"{tg / hdl:.2f}", "formula": f"TG ({tg:g}) ÷ HDL ({hdl:g}) [Target < 2.0]"})
    return results


def get_last_7_dates():
    today = datetime.date.today()
    return [today - datetime.timedelta(days=(6 - i)) for i in range(7)]


def load_entry(entry):
    st.session_state.active_id = entry["id"]
    st.session_state.doc_name = entry["doc_name"]
    st.session_state.saved_at = entry["saved_at"]
    st.session_state.raw_text = entry["raw_text"]
    st.session_state.report_data = entry["report_json"]
    st.session_state.streak_dates = list(entry["streak_dates"])
    st.session_state.tts_audio = None
    for d in get_last_7_dates():
        st.session_state[f"date_{d.isoformat()}"] = (d.isoformat() in st.session_state.streak_dates)


def main():
    init_db()
    load_css()
    history = get_history()

    if "tts_audio" not in st.session_state:
        st.session_state.tts_audio = None
    if "streak_dates" not in st.session_state:
        st.session_state.streak_dates = []

    if "active_id" not in st.session_state:
        if history:
            load_entry(history[0])
        else:
            st.session_state.active_id = None
            st.session_state.doc_name = ""
            st.session_state.saved_at = ""
            st.session_state.report_data = None
            st.session_state.raw_text = ""

    st.markdown(
        """<div class="card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding:18px 24px;">
        <div><div style="font-size:23px; font-weight:800; letter-spacing:-0.03em;">🩺 MediClear</div>
        <div style="font-size:13.5px; color:#6B7280;">Doctor's Note Plain-English Translator, PDF History Vault & Daily Streak Tracker</div></div>
        <div style="display:flex; gap:8px;"><span class="pill pill-blue">Congressional App Challenge</span>
        <span class="pill pill-green">Auto-Saves PDFs & Calendar Logs</span></div></div>""",
        unsafe_allow_html=True,
    )

    last_7_days = get_last_7_dates()
    last_7_iso = [d.isoformat() for d in last_7_days]

    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    with st.sidebar:
        st.markdown("### Settings & Saved History")
        api_key = st.text_input("Gemini API Key (from .env)", value=env_key, type="password")
        st.divider()
        st.markdown(f"### Past PDFs & Reports ({len(history)})")
        if not history:
            st.caption("No reports saved yet.")
        else:
            for item in history:
                is_cur = item["id"] == st.session_state.active_id
                wk_cnt = sum(1 for d_str in item["streak_dates"] if d_str in last_7_iso)
                sb_c1, sb_c2 = st.columns([4.0, 1.2])
                with sb_c1:
                    if st.button(f"{'Active: ' if is_cur else ''}{item['doc_name']} ({wk_cnt}/7d)", key=f"sb_{item['id']}", width="stretch"):
                        load_entry(item)
                        st.rerun()
                with sb_c2:
                    if st.button("Del", key=f"del_{item['id']}"):
                        delete_report(item["id"])
                        if st.session_state.active_id == item["id"]:
                            st.session_state.active_id = None
                            st.session_state.report_data = None
                        st.rerun()
            st.divider()
            if st.button("Wipe All Saved History", width="stretch"):
                wipe_all_history()
                st.session_state.active_id = None
                st.session_state.report_data = None
                st.rerun()

    tab_main, tab_vault = st.tabs(["Upload & Analyze Lab Report", f"Past Extracted PDFs & History ({len(history)} Saved)"])

    with tab_vault:
        st.subheader("All Previously Extracted PDFs & Doctor's Notes")
        if not history:
            st.info("No saved reports yet. Extract a PDF or doctor's note in the first tab to save it automatically.")
        else:
            rows = [
                {
                    "ID": h["id"],
                    "Document Name": h["doc_name"],
                    "Date Extracted": h["saved_at"],
                    "Extracted Lab Markers": ", ".join([f"{b['name']}: {b['value']:g} {b['unit']} ({b['status']})" for b in h["report_json"].get("labs", [])]),
                    "Last 7 Days": f"{sum(1 for d_str in h['streak_dates'] if d_str in last_7_iso)}/7 Days",
                    "Total Days Logged": f"{len(h['streak_dates'])} Total",
                }
                for h in history
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            pick_id = st.selectbox(
                "Select a Past Report to Open or Delete:",
                options=[h["id"] for h in history],
                format_func=lambda rid: next(f"#{h['id']} — {h['doc_name']} ({h['saved_at']})" for h in history if h["id"] == rid),
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Load Selected Report", type="primary", width="stretch"):
                    load_entry(next(h for h in history if h["id"] == pick_id))
                    st.rerun()
            with c2:
                if st.button("Delete Selected Report", width="stretch"):
                    delete_report(pick_id)
                    if st.session_state.active_id == pick_id:
                        st.session_state.active_id = None
                        st.session_state.report_data = None
                    st.rerun()
            with c3:
                if st.button("Wipe All History", width="stretch"):
                    wipe_all_history()
                    st.session_state.active_id = None
                    st.session_state.report_data = None
                    st.rerun()

            preview = next(h for h in history if h["id"] == pick_id)
            with st.expander("View Original Extracted PDF Text & Full JSON Data"):
                st.code(preview["raw_text"], language="text")
                st.json(preview["report_json"])

    with tab_main:
        with st.expander("Upload a New Lab Report PDF or Paste Doctor's Note", expanded=(st.session_state.report_data is None)):
            col_up, col_txt = st.columns([1.0, 1.3], gap="medium")
            with col_up:
                uploaded_file = st.file_uploader("Upload Lab Report (.pdf or .txt)", type=["pdf", "txt"])
                custom_title = st.text_input("Optional Report Name:", placeholder="e.g., Quest Blood Panel Oct 2026")
            with col_txt:
                pasted_text = st.text_area("Or Paste Your Doctor's Note / Lab Values Here:", height=115, placeholder="Paste your lab numbers or doctor's note here...")

            if st.button("Extract, Save & Generate Action Plan", type="primary"):
                source_text = read_pdf(uploaded_file) if uploaded_file else pasted_text.strip()
                doc_title = custom_title.strip() or (uploaded_file.name if uploaded_file else "Pasted Doctor's Note")

                if not source_text:
                    st.warning("Please upload a PDF file or paste your lab report text first.")
                elif not api_key:
                    st.error("Missing Gemini API Key! Add GEMINI_API_KEY=your_key to your .env file or sidebar.")
                else:
                    with st.spinner("Extracting your report (~3 seconds)..."):
                        try:
                            parsed = analyze_report(source_text, api_key)
                            for item in parsed.get("labs", []):
                                item.update(calc_math(float(item["value"]), float(item["low_limit"]), float(item["high_limit"])))
                            new_id = save_report(doc_title, source_text, parsed, [])
                            load_entry({"id": new_id, "doc_name": doc_title, "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p"), "raw_text": source_text, "report_json": parsed, "streak_dates": []})
                            st.rerun()
                        except Exception as err:
                            st.error(f"Could not parse report: {err}")

        data = st.session_state.report_data
        if not data or not data.get("labs"):
            st.markdown(
                """<div class="card" style="text-align:center; padding:36px 24px;">
                <h3 style="margin:0 0 6px 0;">Waiting for Your Lab Report</h3>
                <p style="color:#6B7280; max-width:580px; margin:0 auto; font-size:14px;">
                Upload a lab report PDF or paste a doctor's note above. Every report you extract is automatically saved to your local database so you can view all past PDFs anytime.</p></div>""",
                unsafe_allow_html=True,
            )
            return

        st.markdown(
            f'<div style="display:flex; justify-content:space-between; align-items:center; background:#EFF6FF; border:1px solid #BFDBFE; border-radius:14px; padding:10px 16px; margin-bottom:14px;">'
            f'<span><strong>Viewing Saved Report:</strong> {html.escape(st.session_state.doc_name)} ({html.escape(st.session_state.saved_at)})</span>'
            f'<span class="pill pill-blue">Saved Report #{st.session_state.active_id}</span></div>',
            unsafe_allow_html=True,
        )

        labs = data["labs"]
        flagged_labs = [b for b in labs if b["status"] in ("High", "Low")]
        optimal_labs = [b for b in labs if b["status"] == "Optimal"]

        # Section 1: Side-by-side clinical values vs plain English
        st.markdown('<span class="section-tag">Plain-English Decoder</span>', unsafe_allow_html=True)
        st.subheader("Understand Your Lab Results")
        left_col, right_col = st.columns(2, gap="large")

        with left_col:
            bars_html = ""
            for b in labs:
                val, low, high, smax = float(b["value"]), float(b["low_limit"]), float(b["high_limit"]), float(b["scale_max"])
                l_pct, w_pct = max(0.0, min(90.0, (low / smax) * 100.0)), max(6.0, min(94.0, ((high - low) / smax) * 100.0))
                p_pct = max(3.0, min(97.0, (val / smax) * 100.0))
                p_col, pill_cls = ("#EF4444", "pill-red") if b["status"] != "Optimal" else ("#10B981", "pill-green")
                bars_html += (
                    f'<div class="card-sm"><div style="display:flex; justify-content:space-between; align-items:center;">'
                    f'<div><strong>{html.escape(b["name"])}</strong><div style="font-size:12px; color:#6B7280;">Normal: {low:g}–{high:g} {html.escape(b["unit"])} (Midpoint: {b["midpoint"]:g})</div></div>'
                    f'<div><span style="font-size:18px; font-weight:800; margin-right:8px;">{val:g} {html.escape(b["unit"])}</span><span class="pill {pill_cls}">{b["status"]}</span></div></div>'
                    f'<div class="track"><div class="zone" style="left:{l_pct:.1f}%; width:{w_pct:.1f}%;"></div><div class="pin" style="left:{p_pct:.1f}%; background:{p_col};"></div></div>'
                    f'<div style="display:flex; justify-content:space-between; font-size:12px; color:#4B5563;">'
                    f'<span>Deviation: <strong>{b["dev_pct"]}% {b["direction"]}</strong></span><span>Gap: <strong>{b["gap"]:g} {html.escape(b["unit"])}</strong></span></div></div>'
                )
            st.markdown(f'<div class="card"><h3 style="font-size:18px; margin:0 0 6px 0;">What Your Doctor\'s Sheet Says</h3><p style="font-size:12.5px; color:#6B7280; margin:0 0 12px 0;">Formula: <code>Deviation % = (|Value − Limit| ÷ Limit) × 100</code></p>{bars_html}</div>', unsafe_allow_html=True)

        with right_col:
            cards_html = "".join([
                f'<div class="card-sm" style="border-left:4px solid #0066EE;"><div style="display:flex; justify-content:space-between; margin-bottom:6px;">'
                f'<strong>{html.escape(b["name"])}</strong><span class="pill {"pill-red" if b["status"] != "Optimal" else "pill-green"}">{b["status"]}</span></div>'
                f'<p style="font-size:14px; margin:0 0 8px 0; line-height:1.5;">{html.escape(b["meaning"])}</p>'
                f'<div style="background:#EFF6FF; border-radius:10px; padding:8px 12px; font-size:12.5px; color:#1E3A8A;"><strong>Why It Matters:</strong> {html.escape(b["why_important"])}</div></div>'
                for b in labs
            ])
            st.markdown(
                f'<div class="card"><h3 style="font-size:18px; margin:0 0 6px 0;">Easy-to-Read Plain English</h3>'
                f'<div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:14px; padding:14px; margin-bottom:12px; font-size:14px; line-height:1.55; font-weight:500;">{html.escape(data.get("summary", ""))}</div>{cards_html}</div>',
                unsafe_allow_html=True,
            )
            if st.button("🔊 Generate & Play Audio Summary Aloud", width="stretch"):
                try:
                    st.session_state.tts_audio = generate_speech_mp3(data.get("summary", "Your summary is ready."))
                except Exception as e:
                    st.warning(f"Audio generation failed: {e}")
            if st.session_state.tts_audio:
                st.audio(st.session_state.tts_audio, format="audio/mp3", autoplay=True)

        extra_eqs = get_clinical_equations(labs)
        if extra_eqs:
            eq_cols = st.columns(len(extra_eqs), gap="medium")
            for idx, eq in enumerate(extra_eqs):
                with eq_cols[idx]:
                    st.markdown(f'<div class="card-sm" style="border-top:4px solid #0066EE;"><div style="font-size:12px; font-weight:700; color:#6B7280;">{html.escape(eq["name"])}</div><div style="font-size:21px; font-weight:800; margin:4px 0;">{html.escape(eq["value"])}</div><div style="font-size:12px; color:#4B5563;">{html.escape(eq["formula"])}</div></div>', unsafe_allow_html=True)

        # Section 2: Action Plan Swaps & Optimal Markers
        st.markdown('<div style="margin-top:18px;"><span class="section-tag" style="background:#10B981;">Daily Action Plan</span></div>', unsafe_allow_html=True)
        st.subheader("Your Personalized Daily Swaps & Healthy Habits to Continue")

        if not flagged_labs:
            st.success("Every lab marker on your report is in the Optimal healthy range! See below for what healthy habits to continue.")

        for b in flagged_labs:
            st.markdown(
                f'<div class="card" style="border-top:4px solid #EF4444;"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">'
                f'<span style="font-size:17px; font-weight:800;">Action Plan for {html.escape(b["name"])} ({b["value"]:g} {html.escape(b["unit"])} — {b["status"]})</span>'
                f'<span class="pill pill-red">Target Range: {b["low_limit"]:g}–{b["high_limit"]:g} {html.escape(b["unit"])}</span></div>'
                f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">'
                f'<div><div style="font-size:13px; font-weight:700;">Swap 1: Daily Nutrition Swap</div><div class="swap-row">'
                f'<div class="box-bad"><div style="font-size:10px; font-weight:800; color:#DC2626;">INSTEAD OF</div><div style="font-size:13px; font-weight:600;">{html.escape(b["food_instead"])}</div></div>'
                f'<div style="text-align:center; font-weight:800;">➔</div>'
                f'<div class="box-good"><div style="font-size:10px; font-weight:800; color:#059669;">TRY THIS</div><div style="font-size:13px; font-weight:700;">{html.escape(b["food_try"])}</div></div></div></div>'
                f'<div><div style="font-size:13px; font-weight:700;">Swap 2: Movement & Lifestyle Habit</div><div class="swap-row">'
                f'<div class="box-bad"><div style="font-size:10px; font-weight:800; color:#DC2626;">INSTEAD OF</div><div style="font-size:13px; font-weight:600;">{html.escape(b["habit_instead"])}</div></div>'
                f'<div style="text-align:center; font-weight:800;">➔</div>'
                f'<div class="box-good"><div style="font-size:10px; font-weight:800; color:#059669;">TRY THIS</div><div style="font-size:13px; font-weight:700;">{html.escape(b["habit_try"])}</div></div></div></div></div></div>',
                unsafe_allow_html=True,
            )

        if optimal_labs:
            with st.expander(f"View {len(optimal_labs)} Optimal Lab Marker(s) — What Healthy Habits to Continue Doing", expanded=(len(flagged_labs) == 0)):
                for b in optimal_labs:
                    keep_tip = b.get("keep_doing") or f"Continue eating whole foods ({b.get('food_try', 'fiber & lean protein')}) and staying active ({b.get('habit_try', 'regular daily walks')})."
                    st.markdown(
                        f'<div class="card-sm" style="border-left:4px solid #10B981;">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                        f'<strong>✓ {html.escape(b["name"])}: {b["value"]:g} {html.escape(b["unit"])}</strong>'
                        f'<span class="pill pill-green">Optimal ({b["low_limit"]:g}–{b["high_limit"]:g} {html.escape(b["unit"])})</span></div>'
                        f'<div style="font-size:13.5px; color:#065F46; margin-top:6px;"><strong>What to Continue:</strong> {html.escape(keep_tip)}</div></div>',
                        unsafe_allow_html=True,
                    )

        # Section 3: Rolling 7-Day Real Calendar Tracker & Past Log History
        st.markdown('<div style="margin-top:18px;"><span class="section-tag" style="background:#FC4C02;">Rolling 7-Day Calendar Streak & Goal Math</span></div>', unsafe_allow_html=True)
        st.subheader("Rolling 7-Day Tracker (Auto-Advances with Today's Date)")

        d_cols = st.columns(7, gap="small")
        updated_dates = set(st.session_state.streak_dates)

        for i, d_obj in enumerate(last_7_days):
            iso_str = d_obj.isoformat()
            chk_key = f"date_{iso_str}"
            if chk_key not in st.session_state:
                st.session_state[chk_key] = (iso_str in updated_dates)
            with d_cols[i]:
                checked = st.session_state[chk_key]
                lbl_top = "Today" if i == 6 else d_obj.strftime("%a")
                lbl_sub = d_obj.strftime("%m/%d")
                st.markdown(
                    f'<div class="day-box {"day-on" if checked else "day-off"}">'
                    f'<div>{"🔥" if checked else "○"}</div>'
                    f'<div style="font-size:12.5px;">{lbl_top}</div>'
                    f'<div style="font-size:11px; opacity:0.8;">{lbl_sub}</div></div>',
                    unsafe_allow_html=True,
                )
                now_checked = st.checkbox(f"{lbl_top} {lbl_sub}", key=chk_key, label_visibility="collapsed")
                if now_checked:
                    updated_dates.add(iso_str)
                else:
                    updated_dates.discard(iso_str)

        st.session_state.streak_dates = sorted(list(updated_dates))
        if st.session_state.active_id is not None:
            update_streak(st.session_state.active_id, st.session_state.streak_dates)

        with st.expander(f"View Complete Past Habit Log History ({len(st.session_state.streak_dates)} Total Days Logged)"):
            log_c1, log_c2 = st.columns([1.2, 2.0])
            with log_c1:
                pick_past_date = st.date_input("Log or Remove Any Past Date:", value=datetime.date.today())
                if st.button("Toggle Selected Date in Log", width="stretch"):
                    p_iso = pick_past_date.isoformat()
                    if p_iso in st.session_state.streak_dates:
                        st.session_state.streak_dates.remove(p_iso)
                    else:
                        st.session_state.streak_dates.append(p_iso)
                    st.session_state.streak_dates = sorted(list(set(st.session_state.streak_dates)))
                    if f"date_{p_iso}" in st.session_state:
                        st.session_state[f"date_{p_iso}"] = (p_iso in st.session_state.streak_dates)
                    if st.session_state.active_id is not None:
                        update_streak(st.session_state.active_id, st.session_state.streak_dates)
                    st.rerun()
            with log_c2:
                if st.session_state.streak_dates:
                    st.write("**All Saved Completion Dates for This Report:**")
                    st.code(", ".join(st.session_state.streak_dates), language="text")
                else:
                    st.caption("No dates logged yet. Check off days above to start your log.")

        streak_count = sum(1 for d_str in last_7_iso if d_str in st.session_state.streak_dates)
        adherence_ratio = streak_count / 7.0
        adherence_pct = round(adherence_ratio * 100.0, 1)

        chosen_lab_name = st.radio("Select Lab Marker to View Target Gap Math:", [b["name"] for b in labs], horizontal=True)
        active_lab = next((b for b in labs if b["name"] == chosen_lab_name), labs[0])

        v_start, v_target = float(active_lab["value"]), float(active_lab["target_bound"])
        days_arr = np.arange(0, 31, dtype=float)
        baseline_line = np.full_like(days_arr, v_start)
        projected_line = v_start + (v_target - v_start) * adherence_ratio * (days_arr / 30.0)
        day30_val = float(projected_line[-1])

        m1, m2, m3 = st.columns(3, gap="medium")
        with m1:
            st.markdown(f'<div class="card-sm"><div style="font-size:12px; font-weight:700; color:#6B7280;">LAST 7 DAYS STREAK</div><div style="font-size:28px; font-weight:800; color:#FC4C02;">{streak_count} / 7 Days ({adherence_pct}%)</div><div style="font-size:12px; color:#6B7280;">Total All-Time Logged: {len(st.session_state.streak_dates)} day(s)</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="card-sm"><div style="font-size:12px; font-weight:700; color:#6B7280;">GAP TO NORMAL LIMIT</div><div style="font-size:28px; font-weight:800; color:#0066EE;">{active_lab["gap"]:g} {html.escape(active_lab["unit"])}</div><div style="font-size:12px; color:#6B7280;">Current: {v_start:g} ➔ Healthy Boundary: {v_target:g}</div></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="card-sm"><div style="font-size:12px; font-weight:700; color:#6B7280;">DAY-30 TARGET VALUE</div><div style="font-size:28px; font-weight:800; color:#10B981;">{day30_val:.2f} {html.escape(active_lab["unit"])}</div><div style="font-size:12px; color:#6B7280;">Linearly closes {adherence_pct}% of gap at current streak</div></div>', unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_hrect(y0=float(active_lab["low_limit"]), y1=float(active_lab["high_limit"]), fillcolor="rgba(16,185,129,0.12)", line_width=1, line_dash="dot", line_color="#10B981", annotation_text=f"Healthy Reference Zone ({active_lab['low_limit']:g}–{active_lab['high_limit']:g} {active_lab['unit']})", annotation_font=dict(color="#059669"))
        fig.add_trace(go.Scatter(x=days_arr, y=baseline_line, mode="lines", name="Unchanged Baseline", line=dict(color="#9CA3AF", width=2, dash="dash")))
        fig.add_trace(go.Scatter(x=days_arr, y=projected_line, mode="lines+markers", name=f"Target Gap Closure ({streak_count}/7 Days)", line=dict(color="#10B981" if streak_count >= 5 else "#FC4C02", width=4)))
        fig.update_layout(
            template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
            font=dict(color="#111827", family="Inter, sans-serif"),
            height=320, margin=dict(l=20, r=20, t=30, b=20),
            xaxis=dict(title="Days (0 to 30)", color="#111827", gridcolor="#F3F4F6"),
            yaxis=dict(title=f"{active_lab['name']} ({active_lab['unit']})", color="#111827", gridcolor="#F3F4F6"),
            legend=dict(orientation="h", y=1.12, x=1, xanchor="right", font=dict(color="#111827")),
        )
        st.plotly_chart(fig, width="stretch")

        # Section 4: Printable Doctor Visit Summary
        st.markdown('<div style="margin-top:14px;"><span class="section-tag">Doctor Visit Handoff</span></div>', unsafe_allow_html=True)
        st.subheader("30-Second Doctor Visit Summary")
        today = datetime.date.today().strftime("%B %d, %Y")
        lines = []
        for b in labs:
            if b["status"] == "Optimal":
                lines.append(f"• {b['name']}: {b['value']:g} {b['unit']} [Optimal — Within {b['low_limit']:g}–{b['high_limit']:g} {b['unit']}] | Continue healthy routine")
            else:
                lines.append(f"• {b['name']}: {b['value']:g} {b['unit']} [{b['status']}, {b['dev_pct']}% {b['direction']}] | Swaps: {b['food_try']} & {b['habit_try']}")
        logged_dates_str = ", ".join(st.session_state.streak_dates) if st.session_state.streak_dates else "None logged yet"
        summary_export = (
            f"MEDICLEAR — PATIENT LAB & HABIT SUMMARY ({today})\n"
            f"Document: {st.session_state.doc_name} ({st.session_state.saved_at})\n"
            f"Last 7 Days Streak: {streak_count}/7 Days ({adherence_pct}%) | All Logged Dates: {logged_dates_str}\n\n"
            + "\n".join(lines)
        )
        st.code(summary_export, language="text")
        st.download_button("Download Doctor Summary (.txt)", summary_export, file_name="MediClear_Summary.txt")


if __name__ == "__main__":
    main()