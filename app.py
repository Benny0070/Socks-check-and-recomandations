import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
import base64

# --- 1. CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="PRIME Terminal", page_icon="🛡️", layout="wide")

# --- CSS PERSONALIZAT ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div[data-testid="stMetricValue"] { background-color: transparent !important; }
    div[data-testid="stMetricLabel"] { background-color: transparent !important; }
    .stMetric { background-color: transparent !important; border: none !important; }
    .stButton button { width: 100%; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- INIȚIALIZARE STATE ---
# Aici tinem minte variabilele ca sa nu se piarda la refresh
if 'favorites' not in st.session_state:
    st.session_state.favorites = [] 
if 'favorite_names' not in st.session_state:
    st.session_state.favorite_names = {} 
if 'active_ticker' not in st.session_state:
    st.session_state.active_ticker = "NVDA"

# --- SIDEBAR (METODA SIGURĂ PENTRU TELEFON) ---
st.sidebar.header(f"🔎 Activ: {st.session_state.active_ticker}")

st.sidebar.markdown("---")
st.sidebar.write("**1. Căutare Manuală:**")

# 1. CĂSUȚA DE TEXT (Nu face nimic singură, doar ține textul)
ticker_input = st.sidebar.text_input("Scrie simbolul aici:", placeholder="ex: TSLA", key="input_manual")

# 2. BUTONUL DE EXECUTIE (Asta e 'întârzierea' - execută doar când apeși)
if st.sidebar.button("🔍 CAUTĂ ACUM", type="primary"):
    if ticker_input:
        st.session_state.active_ticker = ticker_input.upper()
        st.rerun() # Refresh forțat
    else:
        st.sidebar.warning("Scrie ceva mai întâi!")

st.sidebar.markdown("---")

# Butonul de Favorite
if st.sidebar.button("➕ Adaugă activ la Favorite"):
    ticker_to_add = st.session_state.active_ticker
    if ticker_to_add not in st.session_state.favorites:
        try:
            t_info = yf.Ticker(ticker_to_add).info
            long_name = t_info.get('longName', ticker_to_add)
            st.session_state.favorites.append(ticker_to_add)
            st.session_state.favorite_names[ticker_to_add] = long_name
            st.sidebar.success("Adăugat!")
            st.rerun()
        except:
            st.sidebar.error("Eroare!")

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
    st.sidebar.info("Nicio companie salvată.")

# --- 2. FUNCȚII UTILITARE ---

def clean_text_for_pdf(text):
    text = str(text)
    text = text.replace("🔴", "[ROSU]").replace("🟢", "[VERDE]").replace("🟡", "[GALBEN]").replace("⚪", "[NEUTRU]")
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
    
    # 1. Trend
    if not history.empty:
        sma = history['Close'].mean() 
        current = history['Close'].iloc[-1]
        if current > sma:
            score += 20
            reasons.append("Trend Ascendent")
    
    # 2. Profitabilitate
    pm = info.get('profitMargins', 0) or 0
    if pm > 0.15: 
        score += 20
        reasons.append(f"Marja Profit: {pm*100:.1f}%")
        
    # 3. Creștere
    rg = info.get('revenueGrowth', 0) or 0
    if rg > 0.10: 
        score += 20
        reasons.append(f"Crestere Venituri: {rg*100:.1f}%")
        
    # 4. Evaluare
    pe = info.get('trailingPE', 0) or 0
    if 0 < pe < 40:
        score += 20
        reasons.append(f"P/E Ratio: {pe:.2f}")
    
    # 5. Cash
    cash = info.get('totalCash', 0) or 0
    debt = info.get('totalDebt', 0) or 0
    if cash > debt:
        score += 20
        reasons.append("Cash > Datorii")
        
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
        
        pos = ['beat', 'rise', 'jump', 'buy', 'growth', 'strong', 'record']
        neg = ['miss', 'fall', 'drop', 'sell', 'weak', 'loss', 'crash']
        val = 0
        for h in headlines:
            if any(x in h.lower() for x in pos): val += 1
            if any(x in h.lower() for x in neg): val -= 1
            
        sent = "Pozitiv 🟢" if val > 0 else "Negativ 🔴" if val < 0 else "Neutru ⚪"
        return sent, headlines
    except:
        return "Indisponibil", []

def create_extended_pdf(ticker, full_name, price, score, reasons, verdict, risk, info):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"AUDIT: {ticker}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Pret: ${price:.2f} | Scor: {score}/100", ln=True)
    pdf.cell(0, 10, f"Verdict: {clean_text_for_pdf(verdict)}", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Motive Scor:", ln=True)
    pdf.set_font("Arial", '', 11)
    for r in reasons:
        pdf.cell(0, 8, f"- {clean_text_for_pdf(r)}", ln=True)
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- MAIN APP ---
temp_stock = yf.Ticker(st.session_state.active_ticker)
try:
    temp_name = temp_stock.info.get('longName', st.session_state.active_ticker)
except:
    temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker}")
st.caption(f"{temp_name}")

perioada = st.select_slider("Perioada:", options=['1mo', '3mo', '6mo', '1y', '2y', '5y'], value='1y')

# TABURILE
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Analiză", "📈 Tehnic", "📅 Calendar", "📰 Știri", "💰 Dividende", "📋 Audit", "⚔️ Vs"
])

stock, history, info = get_stock_data(st.session_state.active_ticker, period=perioada)

if stock and not history.empty:
    curr_price = history['Close'].iloc[-1]
    daily_ret = history['Close'].pct_change().dropna()
    volatility = daily_ret.std() * np.sqrt(252) * 100
    max_dd = ((history['Close'] / history['Close'].cummax()) - 1).min() * 100
    score, reasons = calculate_prime_score(info, history)
    
    if max_dd < -35: verdict = "Risc Ridicat 🔴"; style = "error"
    elif score > 75: verdict = "Oportunitate 🟢"; style = "success"
    else: verdict = "Neutru 🟡"; style = "warning"

    with tab1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Preț", f"${curr_price:.2f}")
        c2.metric("Scor", f"{score}/100")
        c3.metric("Risc", f"{volatility:.1f}%")
        
        if style == "success": st.success(verdict)
        elif style == "warning": st.warning(verdict)
        else: st.error(verdict)
        
        st.line_chart(history['Close'])

    with tab2: # TEHNIC & INSIDERS
        st.subheader("RSI Momentum")
        rsi = calculate_rsi(history['Close']).iloc[-1]
        st.metric("RSI (14)", f"{rsi:.2f}")
        if rsi > 70: st.warning("Supra-cumparat (>70)")
        elif rsi < 30: st.success("Supra-vandut (<30)")
        
        st.markdown("---")
        st.subheader("Insider Trading")
        try:
            ins = stock.insider_transactions
            if ins is not None and not ins.empty:
                st.dataframe(ins.head(10)[['Start Date', 'Insider', 'Shares', 'Text']])
            else:
                st.info("Fara date insideri.")
        except: st.info("Indisponibil.")

    with tab3: # CALENDAR
        try:
            cal = stock.calendar
            if cal is not None and not cal.empty: st.dataframe(cal)
            else: st.write("Fara date calendar.")
        except: st.error("Eroare.")

    with tab4: # STIRI
        s, heads = get_news_sentiment(stock)
        st.write(f"Sentiment: **{s}**")
        for h in heads: st.markdown(f"- {h}")

    with tab5: # DIVIDENDE
        dy = info.get('dividendYield', 0) or 0
        st.metric("Randament", f"{dy*100:.2f}%")
        if dy > 0:
            inv = st.number_input("Investitie ($)", 1000.0)
            st.success(f"Lunar: ${(inv*dy)/12:.2f}")

    with tab6: # PDF
        if st.button("Genereaza PDF"):
            try:
                risk_data = {'vol': volatility, 'dd': max_dd}
                pdf_bytes = create_extended_pdf(st.session_state.active_ticker, temp_name, curr_price, score, reasons, verdict, risk_data, info)
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Audit.pdf">📥 Descarca</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e: st.error(str(e))

    with tab7: # COMPARATIE
        if len(st.session_state.favorites) >= 2:
            sel = st.multiselect("Alege:", st.session_state.favorites, default=st.session_state.favorites[:2])
            if sel:
                df = pd.DataFrame()
                for t in sel:
                    h = yf.Ticker(t).history(period="1y")['Close']
                    if not h.empty: df[t] = (h/h.iloc[0]-1)*100
                st.line_chart(df)
        else: st.info("Adauga 2 favorite pt comparatie.")

else:
    st.error(f"Nu am găsit date pentru {st.session_state.active_ticker}. Verifică simbolul.")
