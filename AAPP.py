import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64
import os
import plotly.graph_objects as go 
import time

# --- 1. CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="PRIME Terminal", page_icon="🛡️", layout="wide")

# =========================================================
# NIVEL 1: SECURITATE (LOGIN)
# =========================================================
def check_access_password():
    if st.session_state.get('access_granted', False):
        return True

    st.markdown("## 🔒 Terminal Privat")
    password_input = st.text_input("Parola Acces", type="password", key="login_pass")
    
    if st.button("Intră în Aplicație"):
        # Parola default 1234 dacă nu e setată în secrets
        secret_access = st.secrets.get("ACCESS_PASSWORD", "1234") 
        if password_input == secret_access:
            st.session_state['access_granted'] = True
            st.rerun()
        else:
            st.error("⛔ Parolă greșită.")
    return False

if not check_access_password():
    st.stop()

# =========================================================
# LOGICA PRINCIPALĂ
# =========================================================

# --- CSS ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div[data-testid="stForm"] button {
        background-color: #00cc00 !important;
        color: black !important;
        font-weight: bold !important;
        border: none !important;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE ---
DB_FILE = "prime_favorites.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                import json
                return json.load(f)
        except: pass
    return {"favorites": [], "names": {}}

def save_db(fav_list, fav_names):
    import json
    with open(DB_FILE, "w") as f:
        json.dump({"favorites": fav_list, "names": fav_names}, f)

if 'db_loaded' not in st.session_state:
    data = load_db()
    st.session_state.favorites = data.get("favorites", [])
    st.session_state.favorite_names = data.get("names", {})
    st.session_state.db_loaded = True

if 'active_ticker' not in st.session_state: 
    st.session_state.active_ticker = "NVDA"

# --- FUNCȚII CALCUL ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_risk_metrics(history):
    if history.empty: return 0, 0, 0
    daily_ret = history['Close'].pct_change().dropna()
    volatility = daily_ret.std() * np.sqrt(252) * 100
    max_dd = ((history['Close'] / history['Close'].cummax()) - 1).min() * 100
    risk_free_rate = 0.04
    mean_return = daily_ret.mean() * 252
    std_dev = daily_ret.std() * np.sqrt(252)
    sharpe = (mean_return - risk_free_rate) / std_dev if std_dev != 0 else 0
    return volatility, max_dd, sharpe

def calculate_prime_score(info, history):
    score = 0
    reasons = []
    
    if not info:
        return 50, ["Date insuficiente (Eroare Yahoo)"]

    # 1. TREND
    if not history.empty:
        sma = history['Close'].mean()
        current = history['Close'].iloc[-1]
        if current > sma:
            score += 20
            reasons.append("Trend Ascendent")

    # 2. EVALUARE
    peg = info.get('pegRatio')
    if peg and 0 < peg < 2.0:
        score += 20
        reasons.append(f"Preț Bun (PEG: {peg:.2f})")
    elif info.get('trailingPE', 100) < 25: 
        score += 10
        reasons.append("P/E Decent (<25)")

    # 3. EFICIENȚĂ
    roe = info.get('returnOnEquity', 0)
    if roe and roe > 0.15:
        score += 20
        reasons.append(f"Eficient (ROE: {roe*100:.1f}%)")

    # 4. CREȘTERE & CASH
    rg = info.get('revenueGrowth', 0)
    if rg and rg > 0.10: 
        score += 20
        reasons.append(f"Creștere Venituri: {rg*100:.1f}%")

    if (info.get('totalCash', 0) > info.get('totalDebt', 0)):
        score += 20
        reasons.append("Bilanț Solid (Cash > Datorii)")

    return score, reasons

# --- DATA FETCHING SIMPLIFICAT (FARA SESIUNI CUSTOM) ---
@st.cache_data(ttl=900, show_spinner=False) # Cache 15 min
def get_safe_data(ticker, period):
    # AICI ERA EROAREA: Am scos 'session=session'
    # Lăsăm yfinance să se ocupe singur
    stock = yf.Ticker(ticker)
    
    try:
        # history() este robust
        history = stock.history(period=period)
    except Exception as e:
        print(f"Eroare istoric: {e}")
        history = pd.DataFrame()

    try:
        # info() este sensibil, îl izolăm
        info = stock.info
    except Exception as e:
        print(f"Eroare info: {e}")
        info = {}
    
    return history, info

# --- PDF GENERATOR ---
def clean_text_for_pdf(text):
    if text is None: return ""
    text = str(text)
    replacements = {'ă':'a', 'â':'a', 'î':'i', 'ș':'s', 'ț':'t', 'Ă':'A', 'Â':'A', 'Î':'I', 'Ș':'S', 'Ț':'T', '🔴':'[RISC]', '🟢':'[BUN]', '🟡':'[NEUTRU]', '💎':'[GEM]'}
    for k, v in replacements.items(): text = text.replace(k, v)
    return text.encode('latin-1', 'ignore').decode('latin-1')

def create_extended_pdf(ticker, price, score, reasons, verdict, risk, info, rsi_val):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 24)
    pdf.cell(0, 20, f"RAPORT: {clean_text_for_pdf(ticker)}", ln=True, align='C')
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"SCOR: {score}/100 | {clean_text_for_pdf(verdict)}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(0, 8, clean_text_for_pdf(f"Pret: ${price:.2f}. Volatilitate: {risk['vol']:.1f}%. Sharpe: {risk['sharpe']:.2f}."))
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "PUNCTE CHEIE:", ln=True)
    pdf.set_font("Arial", '', 12)
    for r in reasons: pdf.cell(0, 8, f"- {clean_text_for_pdf(r)}", ln=True)
    
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "DATE FINANCIARE:", ln=True)
    pdf.set_font("Arial", '', 12)
    
    pe = info.get('trailingPE', 'N/A')
    peg = info.get('pegRatio', 'N/A')
    profit = info.get('profitMargins', 0)
    
    pdf.cell(0, 8, f"P/E Ratio: {pe}", ln=True)
    pdf.cell(0, 8, f"PEG Ratio: {peg}", ln=True)
    pdf.cell(0, 8, f"Marja Profit: {profit*100:.1f}%", ln=True)
    pdf.cell(0, 8, f"RSI (Momentum): {rsi_val:.2f}", ln=True)

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- INTERFAȚA ---

# Sidebar
st.sidebar.title(f"🔍 {st.session_state.active_ticker}")
with st.sidebar.form(key='search_form'):
    c_in, c_btn = st.columns([0.7, 0.3])
    search_val = c_in.text_input("Simbol", label_visibility="collapsed")
    if c_btn.form_submit_button('GO') and search_val:
        st.session_state.active_ticker = search_val.upper()
        st.rerun()

st.sidebar.markdown("---")
# Admin
admin_pass = st.sidebar.text_input("Admin Pass", type="password")
IS_ADMIN = (admin_pass == st.secrets.get("ADMIN_PASSWORD", "admin"))
if IS_ADMIN:
    if st.sidebar.button("➕ Adaugă la Favorite"):
        if st.session_state.active_ticker not in st.session_state.favorites:
            st.session_state.favorites.append(st.session_state.active_ticker)
            save_db(st.session_state.favorites, st.session_state.favorite_names)
            st.rerun()

# Lista Favorite
st.sidebar.subheader("Lista Mea")
for fav in st.session_state.favorites:
    col1, col2 = st.sidebar.columns([4,1])
    if col1.button(fav, key=f"btn_{fav}"):
        st.session_state.active_ticker = fav
        st.rerun()
    if IS_ADMIN and col2.button("X", key=f"del_{fav}"):
        st.session_state.favorites.remove(fav)
        save_db(st.session_state.favorites, st.session_state.favorite_names)
        st.rerun()

if st.sidebar.button("Logout"):
    st.session_state['access_granted'] = False
    st.rerun()

# Main Content
st.title(f"🛡️ {st.session_state.active_ticker}")

# Apelăm funcția reparată
history, info = get_safe_data(st.session_state.active_ticker, "1y")

if history is not None and not history.empty:
    curr_price = history['Close'].iloc[-1]
    vol, max_dd, sharpe = calculate_risk_metrics(history)
    score, reasons = calculate_prime_score(info, history)
    
    if score > 70: verdict = "BUN / STRONG 🟢"
    elif score > 50: verdict = "NEUTRU 🟡"
    else: verdict = "SLAB / RISC 🔴"

    # Tab-uri
    t1, t2, t3, t4, t5 = st.tabs(["Analiză", "Tehnic", "Dividende", "Raport", "VS"])

    with t1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preț", f"${curr_price:.2f}")
        c2.metric("Scor PRIME", f"{score}/100")
        c3.metric("Volatilitate", f"{vol:.1f}%")
        c4.metric("Sharpe", f"{sharpe:.2f}")
        
        if not info:
            st.warning("⚠️ Datele fundamentale limitate. Se afișează doar date tehnice.")
        
        fig = go.Figure(data=[go.Candlestick(x=history.index, open=history['Open'], high=history['High'], low=history['Low'], close=history['Close'])])
        fig.update_layout(height=400, margin=dict(l=0,r=0,t=0,b=0), template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        rsi = calculate_rsi(history['Close']).iloc[-1]
        st.metric("RSI (14)", f"{rsi:.2f}")

    with t3:
        st.subheader("Calculator Dividende")
        div_yield = info.get('dividendYield', 0) if info else 0
        if div_yield is None: div_yield = 0
        
        st.write(f"Randament anual estimat: **{div_yield*100:.2f}%**")
        suma = st.number_input("Investiție ($)", value=1000)
        venit = suma * div_yield
        st.success(f"Venit Pasiv Anual: ${venit:.2f}")

    with t4:
        if st.button("Generează PDF"):
            try:
                rsi_now = calculate_rsi(history['Close']).iloc[-1]
                pdf_data = create_extended_pdf(
                    st.session_state.active_ticker, curr_price, score, reasons, verdict,
                    {'vol': vol, 'sharpe': sharpe}, info if info else {}, rsi_now
                )
                b64 = base64.b64encode(pdf_data).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="{st.session_state.active_ticker}_Raport.pdf">📥 Descarcă PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Eroare PDF: {e}")

    with t5:
        if len(st.session_state.favorites) >= 2:
            st.subheader("Comparație Performanță")
            sel = st.multiselect("Companii", st.session_state.favorites, default=st.session_state.favorites[:2])
            if sel:
                df_chart = pd.DataFrame()
                for s in sel:
                    try:
                        h_tmp, _ = get_safe_data(s, "1y")
                        if not h_tmp.empty:
                            df_chart[s] = (h_tmp['Close'] / h_tmp['Close'].iloc[0] - 1) * 100
                    except: pass
                st.line_chart(df_chart)

else:
    st.error(f"Nu s-au putut încărca date pentru {st.session_state.active_ticker}.")
