import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64
from datetime import datetime
import json
import os
import plotly.graph_objects as go 
import requests
import random
import time

# --- 1. CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="PRIME Terminal", page_icon="🛡️", layout="wide")

# =========================================================
# NIVEL 1: SECURITATE LA INTRARE (LOGIN GENERAL)
# =========================================================
def check_access_password():
    """Verifică dacă utilizatorul are dreptul să vadă site-ul."""
    if st.session_state.get('access_granted', False):
        return True

    st.markdown("## 🔒 Terminal Privat")
    st.write("Introdu parola de acces general pentru a vizualiza datele.")
    
    password_input = st.text_input("Parola Acces", type="password", key="login_pass")
    
    if st.button("Intră în Aplicație"):
        # Dacă nu există secret setat, parola e 1234
        secret_access = st.secrets.get("ACCESS_PASSWORD", "1234") 
        
        if password_input == secret_access:
            st.session_state['access_granted'] = True
            st.rerun()
        else:
            st.error("⛔ Parolă de acces greșită.")

    return False

if not check_access_password():
    st.stop()

# =========================================================
# AICI ÎNCEPE APLICAȚIA
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

# --- SISTEM SALVARE (JSON) ---
DB_FILE = "prime_favorites.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {"favorites": [], "names": {}}
    return {"favorites": [], "names": {}}

def save_db(fav_list, fav_names):
    with open(DB_FILE, "w") as f:
        json.dump({"favorites": fav_list, "names": fav_names}, f)

# --- INIȚIALIZARE STATE ---
if 'db_loaded' not in st.session_state:
    data = load_db()
    st.session_state.favorites = data.get("favorites", [])
    st.session_state.favorite_names = data.get("names", {})
    st.session_state.db_loaded = True

if 'active_ticker' not in st.session_state: 
    st.session_state.active_ticker = "NVDA"

# --- FUNCȚII UTILITARE ---

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- FIX PENTRU RATE LIMIT (Blocare Yahoo) ---
def get_custom_session():
    """Generează o sesiune cu identitate aleatorie pentru a păcăli filtrele."""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'
    ]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    })
    return session

# --- FUNCȚIA DE DESCĂRCARE CU RETRY ---
@st.cache_data(ttl=60, show_spinner=False)
def download_safe_data(ticker, period):
    # Încercăm de 3 ori (Retry logic)
    for i in range(3):
        try:
            session = get_custom_session()
            temp_stock = yf.Ticker(ticker, session=session)
            
            # 1. Încercăm să luăm istoricul
            h = temp_stock.history(period=period)
            
            # Dacă istoricul e gol, ceva nu e bine, mai încercăm o dată
            if h.empty:
                time.sleep(1 + i) # Pauză progresivă
                continue
                
            # 2. Încercăm să luăm INFO
            try:
                info = temp_stock.info
            except:
                info = {} # Continuăm doar cu graficul
            
            return h, info

        except Exception as e:
            time.sleep(1)
            continue
            
    # Dacă a eșuat de 3 ori
    return None, None

def get_stock_data(ticker, period="5y"):
    try:
        # Folosim sesiunea și aici pentru obiectul principal
        session = get_custom_session()
        stock = yf.Ticker(ticker, session=session)
        
        # Luăm datele grele din cache
        history, info = download_safe_data(ticker, period)
        
        if history is None or history.empty:
            return None, None, None
            
        return stock, history, info
    except:
        return None, None, None

def calculate_risk_metrics(history):
    if history.empty: return 0, 0, 0
    
    daily_ret = history['Close'].pct_change().dropna()
    
    # 1. Volatilitate
    volatility = daily_ret.std() * np.sqrt(252) * 100
    
    # 2. Max Drawdown
    max_dd = ((history['Close'] / history['Close'].cummax()) - 1).min() * 100
    
    # 3. Sharpe Ratio
    risk_free_rate = 0.04
    mean_return = daily_ret.mean() * 252
    std_dev = daily_ret.std() * np.sqrt(252)
    
    if std_dev == 0: sharpe = 0
    else: sharpe = (mean_return - risk_free_rate) / std_dev
    
    return volatility, max_dd, sharpe

def calculate_prime_score(info, history):
    score = 0
    reasons = []
    
    # Protecție dacă info e gol
    if not info: info = {}

    # 1. TREND
    if not history.empty:
        if len(history) > 200:
            sma = history['Close'].rolling(window=200).mean().iloc[-1]
            trend_name = "SMA200"
        else:
            sma = history['Close'].mean()
            trend_name = "Media Perioadei"
            
        current = history['Close'].iloc[-1]
        if current > sma:
            score += 20
            reasons.append(f"Trend Ascendent (Peste {trend_name})")

    # 2. EVALUARE
    peg = info.get('pegRatio')
    if peg is not None and 0 < peg < 2.0:
        score += 20
        reasons.append(f"Preț Bun pt Creștere (PEG: {peg:.2f})")
    elif info.get('trailingPE', 100) < 25: 
        score += 10
        reasons.append("P/E Decent (<25)")

    # 3. EFICIENȚĂ
    roe = info.get('returnOnEquity', 0) or 0
    if roe > 0.15:
        score += 20
        reasons.append(f"Management Eficient (ROE: {roe*100:.1f}%)")

    # 4. CREȘTERE
    rg = info.get('revenueGrowth', 0) or 0
    if rg > 0.10: 
        score += 20
        reasons.append(f"Creștere Venituri: {rg*100:.1f}%")

    # 5. SIGURANȚĂ
    fcf = info.get('freeCashflow')
    if fcf is not None and fcf > 0:
        score += 20
        reasons.append("Generează Cash (FCF Pozitiv)")
    elif (info.get('totalCash', 0) > info.get('totalDebt', 0)):
        score += 20
        reasons.append("Bilanț Solid (Cash > Datorii)")

    return score, reasons

def get_news_sentiment(stock):
    try:
        news = stock.news
        headlines = []
        if news:
            for n in news[:5]:
                t = n.get('title', '')
                if t and t not in headlines: headlines.append(t)
        if not headlines: return "Neutru", ["Fara stiri recente."]
        pos = ['beat', 'rise', 'jump', 'buy', 'growth', 'strong', 'record', 'profit']
        neg = ['miss', 'fall', 'drop', 'sell', 'weak', 'loss', 'crash', 'risk']
        val = 0
        for h in headlines:
            if any(x in h.lower() for x in pos): val += 1
            if any(x in h.lower() for x in neg): val -= 1
        sent = "Pozitiv 🟢" if val > 0 else "Negativ 🔴" if val < 0 else "Neutru ⚪"
        return sent, headlines
    except:
        return "Indisponibil", []

# --- CURĂȚARE TEXT PENTRU PDF ---
def clean_text_for_pdf(text):
    """Transformă diacriticele în caractere simple pentru a nu crăpa PDF-ul."""
    if text is None: return ""
    text = str(text)
    replacements = {
        'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't',
        'Ă': 'A', 'Â': 'A', 'Î': 'I', 'Ș': 'S', 'Ț': 'T',
        '🔴': '[RISC]', '🟢': '[BUN]', '🟡': '[NEUTRU]', '⚪': '-',
        '💎': '[GEM]', '🛡️': '[SCUT]', '📈': '[UP]', '📉': '[DOWN]'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # Eliminăm orice alt caracter ciudat care nu e latin-1
    return text.encode('latin-1', 'ignore').decode('latin-1')

# --- GENERATORUL DE RAPORT COMPLEX ---
def create_extended_pdf(ticker, full_name, price, score, reasons, verdict, risk, info, rsi_val):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # --- PAGINA 1: REZUMAT ---
    pdf.add_page()
    
    # Titlu
    pdf.set_font("Arial", 'B', 24)
    pdf.cell(0, 20, f"RAPORT DE ANALIZA: {clean_text_for_pdf(ticker)}", ln=True, align='C')
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Generat automat de PRIME Terminal | Data: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(10)

    # 1. SCOR ȘI VERDICT
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "1. VERDICT GENERAL", ln=True, fill=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(50, 10, f"SCOR PRIME: {score}/100", ln=False)
    pdf.cell(0, 10, f"CALIFICATIV: {clean_text_for_pdf(verdict)}", ln=True)
    
    pdf.set_font("Arial", '', 11)
    pdf.ln(5)
    pdf.multi_cell(0, 6, clean_text_for_pdf(
        f"Compania {full_name} se tranzactioneaza la pretul de ${price:.2f}. "
        f"Pe baza algoritmului nostru, aceasta prezinta un profil de risc cu volatilitate anuala de {risk['vol']:.1f}% "
        f"si un Sharpe Ratio de {risk.get('sharpe', 0):.2f} (un numar mai mare de 1 indica un randament bun ajustat la risc)."
    ))

    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "PUNCTE CHEIE (PRO/CONTRA)", ln=True)
    pdf.set_font("Arial", '', 11)
    
    if reasons:
        for r in reasons:
            pdf.cell(5, 8, "-", ln=False)
            pdf.multi_cell(0, 8, clean_text_for_pdf(r))
    else:
        pdf.cell(0, 8, "Nu au fost identificate semnale majore automate.", ln=True)

    # --- PAGINA 2: ANALIZA FUNDAMENTALĂ DETALIATĂ ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "2. ANALIZA FUNDAMENTALA DETALIATA", ln=True, fill=True)
    pdf.ln(5)

    # A. EVALUARE (VALUATION)
    pe = info.get('trailingPE')
    peg = info.get('pegRatio')
    pb = info.get('priceToBook')
    
    # Interpretare Textuala Evaluare
    interp_val = "Date insuficiente."
    if pe:
        if pe < 15: interp_val = "Compania este considerata ieftina (Sub-evaluata)."
        elif pe < 30: interp_val = "Evaluarea este corecta (Fair Value)."
        else: interp_val = "Pretul include asteptari mari de crestere (Supra-evaluata)."
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"A. Evaluare (Cat platesti?): {clean_text_for_pdf(interp_val)}", ln=True)
    pdf.set_font("Arial", '', 11)
    
    col_w = 60
    pdf.cell(col_w, 8, f"P/E Ratio: {pe if pe else 'N/A'}", border=1)
    pdf.cell(col_w, 8, f"PEG Ratio: {peg if peg else 'N/A'}", border=1)
    pdf.cell(col_w, 8, f"P/Book: {pb if pb else 'N/A'}", border=1, ln=True)
    pdf.ln(5)

    # B. PROFITABILITATE
    mg = info.get('profitMargins', 0)
    roe = info.get('returnOnEquity', 0)
    
    # Interpretare Textuala Profit
    interp_prof = "Compania are probleme de profitabilitate."
    if mg > 0.15: interp_prof = "Compania este o masina de bani (Marje foarte bune)."
    elif mg > 0.05: interp_prof = "Profitabilitate stabila si normala."
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"B. Profitabilitate: {clean_text_for_pdf(interp_prof)}", ln=True)
    pdf.set_font("Arial", '', 11)
    
    pdf.cell(col_w, 8, f"Marja Profit: {mg*100:.1f}%", border=1)
    pdf.cell(col_w, 8, f"ROE (Randament): {roe*100:.1f}%", border=1)
    pdf.cell(col_w, 8, f"Revenue Growth: {info.get('revenueGrowth', 0)*100:.1f}%", border=1, ln=True)
    pdf.ln(5)

    # C. BILANT SI DATORII
    cash = info.get('totalCash', 0)
    debt = info.get('totalDebt', 0)
    current_ratio = info.get('currentRatio', 0)
    
    interp_health = "Situatie financiara riscanta."
    if cash > debt: interp_health = "Bilant FORTAREATA (Mai multi bani decat datorii)."
    elif current_ratio > 1.5: interp_health = "Stabilitate buna pe termen scurt."
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"C. Sanatate Financiara: {clean_text_for_pdf(interp_health)}", ln=True)
    pdf.set_font("Arial", '', 11)
    
    pdf.cell(col_w, 8, f"Cash Total: ${cash/1e9:.1f}B", border=1)
    pdf.cell(col_w, 8, f"Datorie Totala: ${debt/1e9:.1f}B", border=1)
    pdf.cell(col_w, 8, f"Lichiditate (Curr): {current_ratio:.2f}", border=1, ln=True)

    # --- PAGINA 3: TEHNIC, DIVIDENDE SI DISCLAIMER ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "3. ANALIZA TEHNICA & DIVIDENDE", ln=True, fill=True)
    pdf.ln(5)

    # RSI
    interp_rsi = "Momentum Neutru."
    if rsi_val > 70: interp_rsi = "Supra-cumparat (Posibila corectie)."
    elif rsi_val < 30: interp_rsi = "Supra-vandut (Posibila revenire)."
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"Indicator RSI (14 zile): {rsi_val:.2f} -> {clean_text_for_pdf(interp_rsi)}", ln=True)
    
    # Dividende
    div_yield = info.get('dividendYield', 0)
    if div_yield and div_yield < 1: div_yield = div_yield * 100 # Corectie
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Politica de Dividende:", ln=True)
    pdf.set_font("Arial", '', 11)
    if div_yield and div_yield > 0:
        pdf.multi_cell(0, 6, clean_text_for_pdf(
            f"Compania plateste dividende. Randamentul anual curent este de {div_yield:.2f}%. "
            f"Rata de plata (Payout Ratio) este de {info.get('payoutRatio', 0)*100:.1f}%, ceea ce indica cat din profit se intoarce la investitori."
        ))
    else:
        pdf.multi_cell(0, 6, "Compania NU plateste dividende in prezent. Profitul este reinvestit.")

    # TABEL DATE BRUTE SUPLIMENTARE
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Alte Date Relevante (Snapshot):", ln=True)
    pdf.set_font("Arial", '', 10)
    
    extra_data = [
        ("Sector", info.get('sector', 'N/A')),
        ("Industrie", info.get('industry', 'N/A')),
        ("Angajati", info.get('fullTimeEmployees', 'N/A')),
        ("Target Pret Analisti", f"${info.get('targetMeanPrice', 'N/A')}"),
        ("Beta (Volatilitate vs Piata)", f"{info.get('beta', 'N/A')}")
    ]
    
    for label, val in extra_data:
        pdf.cell(60, 6, clean_text_for_pdf(label), border=1)
        pdf.cell(0, 6, clean_text_for_pdf(str(val)), border=1, ln=True)

    # DISCLAIMER FINAL
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5, clean_text_for_pdf(
        "DISCLAIMER: Acest raport este generat automat de un algoritm software si are scop pur informativ. "
        "Nu reprezinta un sfat financiar, juridic sau fiscal. Performantele trecute nu garanteaza rezultate viitoare. "
        "Consultati un specialist inainte de a investi."
    ))

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SIDEBAR (SEARCH) ---
st.sidebar.title(f"🔍 {st.session_state.active_ticker}")
st.sidebar.write("Căutare Nouă:")

with st.sidebar.form(key='search_form'):
    c_in, c_btn = st.columns([0.7, 0.3])
    with c_in:
        search_val = st.text_input("Simbol", placeholder="TSLA", label_visibility="collapsed")
    with c_btn:
        submit_button = st.form_submit_button(label='GO')
    if submit_button and search_val:
        st.session_state.active_ticker = search_val.upper()
        st.rerun()

st.sidebar.markdown("---")

# ZONA ADMIN SIDEBAR
st.sidebar.caption("🔧 Zonă Administrator")
admin_input = st.sidebar.text_input("Parola Editare", type="password", placeholder="Pentru a modifica lista...")
secret_admin_key = st.secrets.get("ADMIN_PASSWORD", "admin_secret")
IS_ADMIN = (admin_input == secret_admin_key)

if IS_ADMIN:
    st.sidebar.success("✅ Mod Editare Activ")
    if st.sidebar.button("➕ Adaugă la Favorite"):
        ticker_to_add = st.session_state.active_ticker
        if ticker_to_add not in st.session_state.favorites:
            try:
                # Facem fetch cu sesiunea sigură
                sess = get_custom_session()
                t_info = yf.Ticker(ticker_to_add, session=sess).info
                long_name = t_info.get('longName', ticker_to_add)
                st.session_state.favorites.append(ticker_to_add)
                st.session_state.favorite_names[ticker_to_add] = long_name
                save_db(st.session_state.favorites, st.session_state.favorite_names)
                st.sidebar.success("Salvat!")
                st.rerun()
            except Exception: st.sidebar.error("Eroare!")
else:
    if st.session_state.active_ticker not in st.session_state.favorites:
        st.sidebar.info("🔒 Loghează-te ca Admin pentru a adăuga.")

st.sidebar.subheader("Lista Mea")
if st.session_state.favorites:
    for fav in st.session_state.favorites:
        full_n = st.session_state.favorite_names.get(fav, fav)
        if IS_ADMIN:
            c1, c2 = st.sidebar.columns([4, 1])
        else:
            c1 = st.sidebar 
        
        def set_fav(f=fav): st.session_state.active_ticker = f
        def del_fav(f=fav): 
            st.session_state.favorites.remove(f)
            save_db(st.session_state.favorites, st.session_state.favorite_names)

        if IS_ADMIN:
            c1.button(f"{fav}", key=f"btn_{fav}", on_click=set_fav, help=full_n)
            c2.button("X", key=f"del_{fav}", on_click=del_fav) 
        else:
            st.sidebar.button(f"{fav}", key=f"btn_{fav}", on_click=set_fav, help=full_n)
else:
    st.sidebar.info("Lista este goală.")

st.sidebar.markdown("---")
if st.sidebar.button("🔒 Logout Site"):
    st.session_state['access_granted'] = False
    st.rerun()

# --- MAIN APP (PUBLIC DUPA ACCES) ---
# Pre-incarcare nume
try: 
    temp_stock_sess = yf.Ticker(st.session_state.active_ticker, session=get_custom_session())
    temp_name = temp_stock_sess.info.get('longName', st.session_state.active_ticker)
except: 
    temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker}")
st.caption(f"{temp_name}")

optiuni_ani = ['1mo', '3mo', '6mo', '1y', '2y', '3y', '5y', 'max']
perioada = st.select_slider("Perioada:", options=optiuni_ani, value='1y')

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Analiză", "📈 Tehnic", "📅 Calendar", "📰 Știri", "💰 Dividende", "📋 Audit (PDF)", "⚔️ Vs"
])

stock, history, info = get_stock_data(st.session_state.active_ticker, period=perioada)

if stock and history is not None and not history.empty:
    curr_price = history['Close'].iloc[-1]
    
    volatility, max_dd, sharpe = calculate_risk_metrics(history)
    score, reasons = calculate_prime_score(info, history)
    
    if max_dd < -50: verdict = "Prăbușire Istorică 🔴"; style = "error"
    elif sharpe > 1.0 and score > 70: verdict = "💎 GEM (Oportunitate)"; style = "success"
    elif score > 60: verdict = "Solid 🟢"; style = "success"
    else: verdict = "Neutru / Riscant 🟡"; style = "warning"

    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preț", f"${curr_price:.2f}")
        c2.metric("Scor PRIME", f"{score}/100")
        c3.metric("Risc (Vol)", f"{volatility:.1f}%")
        c4.metric("Sharpe Ratio", f"{sharpe:.2f}")
        
        if style == "success": st.success(verdict)
        elif style == "warning": st.warning(verdict)
        else: st.error(verdict)
        
        fig = go.Figure(data=[go.Candlestick(
            x=history.index,
            open=history['Open'],
            high=history['High'],
            low=history['Low'],
            close=history['Close'],
            name=st.session_state.active_ticker
        )])
        fig.update_layout(
            yaxis_title='Preț ($)',
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=20, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2: 
        st.subheader("RSI Momentum")
        rsi_val = calculate_rsi(history['Close']).iloc[-1]
        st.metric("RSI (14)", f"{rsi_val:.2f}")
        if rsi_val > 70: st.warning("Supra-cumparat (>70)")
        elif rsi_val < 30: st.success("Supra-vandut (<30)")
        st.markdown("---")
        st.subheader("Insider Trading")
        try:
            ins = stock.insider_transactions
            if ins is not None and not ins.empty: st.dataframe(ins.head(10)[['Start Date', 'Insider', 'Shares', 'Text']])
            else: st.info("Fara date insideri.")
        except: st.info("Indisponibil.")

    with tab3:
        try:
            cal = stock.calendar
            if cal is not None and not cal.empty: st.dataframe(cal)
            else: st.write("Fara date calendar.")
        except: st.error("Eroare.")

    with tab4:
        s, heads = get_news_sentiment(stock)
        st.write(f"Sentiment: **{s}**")
        for h in heads: st.markdown(f"- {h}")

    with tab5:
        st.subheader("💰 Dividende & Venit Pasiv")
        
        # 1. PRELUARE DATE AUTOMATE
        div_rate = info.get('dividendRate', 0)
        div_yield_raw = info.get('dividendYield', 0)
        
        # Dacă lipsește yield-ul dat de Yahoo, îl calculăm noi brut
        if (div_yield_raw is None or div_yield_raw == 0) and (div_rate and div_rate > 0):
             div_yield_raw = div_rate / curr_price

        # Standardizare
        if div_yield_raw is None: 
            auto_yield = 0.0
        else:
            auto_yield = div_yield_raw * 100

        # 2. ZONA DE CONTROL MANUAL
        col_info, col_edit = st.columns([2, 1])
        
        with col_info:
            st.write(f"Yield detectat automat: **{auto_yield:.2f}%**")
            st.caption(f"Plată anuală (est): ${div_rate if div_rate else 0}")

        with col_edit:
            override = st.checkbox("✏️ Corectează Manual")
        
        if override:
            final_yield = st.number_input("Introdu Randamentul Corect (%):", value=float(auto_yield), step=0.1, format="%.2f")
            st.success(f"Folosim randamentul manual: {final_yield}%")
        else:
            final_yield = auto_yield

        st.markdown("---")

        # 3. CALCULATOR VENIT PASIV
        if final_yield > 0:
            st.subheader("🧮 Calculator Venit Pasiv")
            st.write("Câți bani vrei să investești?")
            
            inv = st.number_input("Suma Investită ($)", min_value=1.0, value=1000.0, step=100.0, key="inv_calc")
            
            venit_anual = inv * (final_yield / 100)
            venit_lunar = venit_anual / 12
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Investiție", f"${inv:,.0f}")
            c2.metric("Venit Lunar", f"${venit_lunar:.2f}")
            c3.metric("Venit Anual", f"${venit_anual:.2f}")
            
            st.progress(min(int(final_yield * 2), 100))
            st.caption(f"La un randament de {final_yield}%, îți recuperezi investiția din dividende în aproximativ {100/final_yield:.1f} ani (fără creșterea prețului).")
            
        else:
            st.info("Această companie nu pare să plătească dividende (0%). Dacă greșesc, bifează 'Corectează Manual' sus.")

    with tab6:
        st.write("Genereaza un raport complet.")
        if st.button("📄 Descarca Raport Complet"):
            try:
                curr_rsi = calculate_rsi(history['Close']).iloc[-1]
                risk_data = {'vol': volatility, 'dd': max_dd, 'sharpe': sharpe}
                
                pdf_bytes = create_extended_pdf(
                    ticker=st.session_state.active_ticker,
                    full_name=temp_name,
                    price=curr_price,
                    score=score,
                    reasons=reasons,
                    verdict=verdict,
                    risk=risk_data,
                    info=info,
                    rsi_val=curr_rsi
                )
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Raport_Audit_{st.session_state.active_ticker}.pdf">📥 Descarca PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e: 
                st.error(f"Eroare generare PDF: {str(e)}")

    with tab7:
        if len(st.session_state.favorites) >= 2:
            st.subheader("🏁 Cursa Prețului (1 An)")
            sel = st.multiselect("Alege companii:", st.session_state.favorites, default=st.session_state.favorites[:2])
            
            if sel:
                df_chart = pd.DataFrame()
                comp_data = [] 
                
                for t in sel:
                    try:
                        # Pauză mică pentru a evita rate limit în loop
                        time.sleep(0.5) 
                        s_tmp = yf.Ticker(t, session=get_custom_session())
                        h = s_tmp.history(period="1y")['Close']
                        i = s_tmp.info
                        
                        if not h.empty: df_chart[t] = (h/h.iloc[0]-1)*100
                        
                        comp_data.append({
                            "Simbol": t,
                            "Preț": i.get('currentPrice'),
                            "P/E (Evaluare)": i.get('trailingPE'),
                            "PEG (Creștere)": i.get('pegRatio'),
                            "Marja Profit": f"{i.get('profitMargins', 0)*100:.1f}%",
                            "Datorie/Cash": "🟢 Bun" if i.get('totalCash', 0) > i.get('totalDebt', 0) else "🔴 Risc"
                        })
                    except: pass
                
                st.line_chart(df_chart)
                
                st.markdown("---")
                st.subheader("⚖️ Comparație Fundamentală")
                if comp_data:
                    df_table = pd.DataFrame(comp_data).set_index("Simbol")
                    st.dataframe(df_table.style.highlight_max(axis=0, color='#004d00'), use_container_width=True)
                    st.caption("*Verde închis indică valoarea cea mai mare din coloană.")
        else:
            st.info("Adaugă minim 2 companii la favorite pentru a activa comparația.")

else:
    st.error(f"Nu am găsit date pentru {st.session_state.active_ticker}. Sistemul Yahoo e supraîncărcat. Reîncarcă pagina în 1 minut.")
