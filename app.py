import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
import base64

# --- 1. CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="PRIME Terminal", page_icon="🛡️", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div[data-testid="stMetricValue"] { background-color: transparent !important; }
    .stButton button { width: 100%; border-radius: 5px; }
    /* Ascundem chenarul formularului pentru aspect curat */
    div[data-testid="stForm"] { border: none; padding: 0; }
    </style>
    """, unsafe_allow_html=True)

# --- INIȚIALIZARE STATE ---
if 'favorites' not in st.session_state:
    st.session_state.favorites = [] 
if 'favorite_names' not in st.session_state:
    st.session_state.favorite_names = {} 
if 'active_ticker' not in st.session_state:
    st.session_state.active_ticker = "NVDA"

# --- FUNCȚII UTILITARE (PDF, RSI, ETC) ---
def clean_text_for_pdf(text):
    text = str(text).replace("🔴", "[ROSU]").replace("🟢", "[VERDE]").replace("🟡", "[GALBEN]").replace("⚪", "[NEUTRU]")
    return text.encode('latin-1', 'ignore').decode('latin-1')

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_stock_data(ticker, period="5y"):
    try:
        stock = yf.Ticker(ticker)
        history = stock.history(period=period)
        info = stock.info
        return stock, history, info
    except:
        return None, None, None

def calculate_prime_score(info, history):
    score = 0
    reasons = []
    if not history.empty:
        sma = history['Close'].mean() 
        current = history['Close'].iloc[-1]
        if current > sma: score += 20; reasons.append("Trend Ascendent")
    pm = info.get('profitMargins', 0) or 0
    if pm > 0.15: score += 20; reasons.append(f"Marja Profit: {pm*100:.1f}%")
    rg = info.get('revenueGrowth', 0) or 0
    if rg > 0.10: score += 20; reasons.append(f"Crestere Venituri: {rg*100:.1f}%")
    pe = info.get('trailingPE', 0) or 0
    if 0 < pe < 40: score += 20; reasons.append(f"P/E Ratio: {pe:.2f}")
    cash = info.get('totalCash', 0) or 0
    debt = info.get('totalDebt', 0) or 0
    if cash > debt: score += 20; reasons.append("Cash > Datorii")
    return score, reasons

def get_news_sentiment(stock):
    try:
        news = stock.news
        headlines = [n.get('title', '') for n in news[:5] if n.get('title')]
        if not headlines: return "Neutru", ["Fara stiri recente."]
        pos = ['beat', 'rise', 'jump', 'buy', 'growth', 'strong']
        neg = ['miss', 'fall', 'drop', 'sell', 'weak', 'loss']
        val = sum([1 for h in headlines if any(x in h.lower() for x in pos)]) - sum([1 for h in headlines if any(x in h.lower() for x in neg)])
        sent = "Pozitiv 🟢" if val > 0 else "Negativ 🔴" if val < 0 else "Neutru ⚪"
        return sent, headlines
    except: return "Indisponibil", []

def create_extended_pdf(ticker, full_name, price, score, reasons, verdict, risk, info):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"AUDIT: {ticker} - {clean_text_for_pdf(full_name)}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%d-%m-%Y')} | Pret: ${price:.2f}", ln=True)
    pdf.cell(0, 10, f"Scor PRIME: {score}/100 | Verdict: {clean_text_for_pdf(verdict)}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "1. Indicatori", ln=True); pdf.set_font("Arial", '', 11)
    lines = [f"ROE: {(info.get('returnOnEquity',0)or 0)*100:.2f}%", f"Beta: {info.get('beta',0)}", f"Datorie/Eq: {info.get('debtToEquity',0)}"]
    for l in lines: pdf.cell(0, 8, f"- {clean_text_for_pdf(l)}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "2. Motive Scor", ln=True); pdf.set_font("Arial", '', 11)
    for r in reasons: pdf.cell(0, 8, f"- {clean_text_for_pdf(r)}", ln=True)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SIDEBAR CU FORMULAR (SOLUȚIA PENTRU ENTER) ---
st.sidebar.header("🔍 Căutare Rapidă")

# AICI ESTE SECRETUL: st.form
# Formularul blochează reîncărcarea paginii până când dai Enter
with st.sidebar.form(key='search_form'):
    # Inputul este în interiorul formularului
    new_ticker_input = st.text_input(
        "Simbol (ex: PLTR, TSLA)", 
        value=st.session_state.active_ticker
    )
    
    # Butonul de submit (invizibil practic, dar necesar pt form)
    # Când dai ENTER într-un text_input din form, se apasă automat acest buton
    submit_button = st.form_submit_button(label='🔎 Caută')

# LOGICA DE DUPĂ SUBMIT
if submit_button:
    # Dacă s-a apăsat Enter sau butonul Caută
    st.session_state.active_ticker = new_ticker_input.upper()
    st.rerun()

# Buton separat pentru Favorite (în afara formularului)
c1_fav, c2_fav = st.sidebar.columns([3,1])
if c1_fav.button("➕ Adaugă la Favorite"):
    curr = st.session_state.active_ticker
    if curr not in st.session_state.favorites:
        try:
            t_info = yf.Ticker(curr).info
            long_name = t_info.get('longName', curr)
            st.session_state.favorites.append(curr)
            st.session_state.favorite_names[curr] = long_name
            st.sidebar.success(f"Salvat!")
        except:
            st.sidebar.error("Eroare!")

st.sidebar.markdown("---")
st.sidebar.subheader("Lista Mea")

if st.session_state.favorites:
    for fav in st.session_state.favorites:
        full_n = st.session_state.favorite_names.get(fav, fav)
        disp_name = (full_n[:18] + '..') if len(full_n) > 18 else full_n
        
        c1, c2 = st.sidebar.columns([4, 1])
        if c1.button(f"{fav}", key=f"btn_{fav}", help=full_n):
            st.session_state.active_ticker = fav
            st.rerun()
        if c2.button("X", key=f"del_{fav}"):
            st.session_state.favorites.remove(fav)
            st.rerun()
else:
    st.sidebar.info("Lista goală.")

# --- MAIN APP ---
temp_stock = yf.Ticker(st.session_state.active_ticker)
try:
    temp_name = temp_stock.info.get('longName', st.session_state.active_ticker)
except:
    temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker} - {temp_name}")

perioada = st.select_slider("Perioada:", options=['1mo', '3mo', '6mo', '1y', '2y', '5y', 'max'], value='1y')

# TABURI
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Analiză", "📈 Tehnic", "📅 Calendar", "📰 Știri", "💰 Dividende", "📋 PDF", "⚔️ Vs"])

stock, history, info = get_stock_data(st.session_state.active_ticker, period=perioada)

if stock and not history.empty:
    curr_price = history['Close'].iloc[-1]
    score, reasons = calculate_prime_score(info, history)
    
    # 1. ANALIZA
    with tab1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Preț", f"${curr_price:.2f}")
        c2.metric("Scor PRIME", f"{score}/100")
        verdict = "Cumpărare 🟢" if score > 70 else "Neutru 🟡"
        c3.metric("Verdict", verdict)
        st.line_chart(history['Close'])

    # 2. TEHNIC
    with tab2:
        rsi = calculate_rsi(history['Close']).iloc[-1]
        st.metric("RSI (Momentum)", f"{rsi:.2f}")
        if rsi > 70: st.warning("Supra-cumpărat (Scump) 🔥")
        elif rsi < 30: st.success("Supra-vândut (Ieftin) 💎")
        else: st.info("Preț Corect ⚖️")
        
        st.write("### Insider Trading")
        try:
            st.dataframe(stock.insider_transactions.head(5))
        except: st.write("Indisponibil")

    # 3. CALENDAR
    with tab3:
        try: st.dataframe(stock.calendar)
        except: st.write("Fără date.")

    # 4. STIRI
    with tab4:
        s, h = get_news_sentiment(stock)
        st.write(f"Sentiment: {s}")
        for x in h: st.markdown(f"- {x}")

    # 5. DIVIDENDE
    with tab5:
        d = info.get('dividendYield', 0) or 0
        st.metric("Randament", f"{d*100:.2f}%")
        
    # 6. PDF
    with tab6:
        if st.button("Generează Raport"):
            risk = {'vol': 0, 'dd': 0} # Simplificat pt stabilitate
            pdf = create_extended_pdf(st.session_state.active_ticker, temp_name, curr_price, score, reasons, verdict, risk, info)
            b64 = base64.b64encode(pdf).decode()
            st.markdown(f'<a href="data:application/octet-stream;base64,{b64}" download="{st.session_state.active_ticker}.pdf">📥 Descarcă</a>', unsafe_allow_html=True)

    # 7. VS
    with tab7:
        if len(st.session_state.favorites) >= 2:
            sel = st.multiselect("Compară:", st.session_state.favorites, default=st.session_state.favorites[:2])
            if sel:
                df = pd.DataFrame()
                for t in sel:
                    h = yf.Ticker(t).history(period="1y")['Close']
                    if not h.empty: df[t] = (h/h.iloc[0]-1)*100
                st.line_chart(df)
        else:
            st.info("Adaugă 2 companii la favorite pentru comparație.")

else:
    st.error(f"Nu am găsit date pentru {st.session_state.active_ticker}. Verifică simbolul.")
