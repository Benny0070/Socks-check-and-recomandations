import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64
from datetime import datetime

# --- 1. CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="PRIME Terminal", page_icon="🛡️", layout="wide")

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

# --- STATE ---
if 'favorites' not in st.session_state: st.session_state.favorites = [] 
if 'favorite_names' not in st.session_state: st.session_state.favorite_names = {} 
if 'active_ticker' not in st.session_state: st.session_state.active_ticker = "NVDA"

# --- FUNCȚII UTILITARE ---
def clean_text_for_pdf(text):
    text = str(text)
    # Înlocuim emoji-urile cu text pentru că FPDF nu suportă emoji standard
    text = text.replace("🔴", "[RISC]").replace("🟢", "[BUN]").replace("🟡", "[NEUTRU]").replace("⚪", "-")
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
            reasons.append("Trend Ascendent (Peste medie)")
    
    # 2. Profitabilitate
    pm = info.get('profitMargins', 0) or 0
    if pm > 0.15: 
        score += 20
        reasons.append(f"Marja Profit Solida: {pm*100:.1f}%")
        
    # 3. Creștere
    rg = info.get('revenueGrowth', 0) or 0
    if rg > 0.10: 
        score += 20
        reasons.append(f"Crestere Venituri: {rg*100:.1f}%")
        
    # 4. Evaluare
    pe = info.get('trailingPE', 0) or 0
    if 0 < pe < 40:
        score += 20
        reasons.append(f"Evaluare Corecta (P/E: {pe:.2f})")
    
    # 5. Cash
    cash = info.get('totalCash', 0) or 0
    debt = info.get('totalDebt', 0) or 0
    if cash > debt:
        score += 20
        reasons.append("Bilant Puternic (Cash > Datorii)")
        
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

# --- GENERARE PDF EXTINS (MODIFICAT) ---
def create_extended_pdf(ticker, full_name, price, score, reasons, verdict, risk, info, rsi_val):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. HEADER
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(0, 15, f"RAPORT DE AUDIT: {ticker}", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Generat la: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(5)

    # 2. REZUMAT EXECUTIV
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "1. REZUMAT EXECUTIV", ln=True, fill=True)
    pdf.ln(2)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(50, 10, f"Companie: {clean_text_for_pdf(full_name)}", ln=True)
    pdf.cell(50, 10, f"Pret Curent: ${price:.2f}", ln=True)
    pdf.cell(50, 10, f"Scor PRIME: {score}/100", ln=True)
    pdf.cell(50, 10, f"Verdict: {clean_text_for_pdf(verdict)}", ln=True)
    
    # 3. ANALIZA TEHNICA & RISC
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "2. PROFIL DE RISC & TEHNIC", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", '', 11)
    
    # Interpretare RSI
    rsi_interp = "Supra-cumparat (Scump)" if rsi_val > 70 else "Supra-vandut (Ieftin)" if rsi_val < 30 else "Neutru"
    
    pdf.cell(95, 8, f"Volatilitate (Risc): {risk['vol']:.1f}%", border=1)
    pdf.cell(95, 8, f"Max Drawdown (Cadere Max): {risk['dd']:.1f}%", border=1, ln=True)
    pdf.cell(95, 8, f"RSI (14): {rsi_val:.2f}", border=1)
    pdf.cell(95, 8, f"Semnal RSI: {rsi_interp}", border=1, ln=True)
    pdf.cell(95, 8, f"High 52 Saptamani: {info.get('fiftyTwoWeekHigh', 'N/A')}", border=1)
    pdf.cell(95, 8, f"Low 52 Saptamani: {info.get('fiftyTwoWeekLow', 'N/A')}", border=1, ln=True)

    # 4. DATE FUNDAMENTALE (VALUARE)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "3. INDICATORI FUNDAMENTALI", ln=True, fill=True)
    pdf.ln(2)
    
    # Helper pentru extragere sigura si formatare
    def get_fmt(key, is_perc=False):
        val = info.get(key)
        if val is None: return "N/A"
        if is_perc: return f"{val*100:.2f}%"
        return f"{val:.2f}"

    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "A. Evaluare (Este pretul corect?)", ln=True)
    pdf.set_font("Arial", '', 11)
    
    pdf.cell(63, 8, f"P/E Ratio: {get_fmt('trailingPE')}", border=1)
    pdf.cell(63, 8, f"Forward P/E: {get_fmt('forwardPE')}", border=1)
    pdf.cell(63, 8, f"PEG Ratio: {get_fmt('pegRatio')}", border=1, ln=True)
    pdf.cell(63, 8, f"Price/Book: {get_fmt('priceToBook')}", border=1)
    pdf.cell(63, 8, f"Price/Sales: {get_fmt('priceToSalesTrailing12Months')}", border=1)
    pdf.cell(63, 8, f"Enterprise Value: {info.get('enterpriseValue', 0)/1e9:.1f}B", border=1, ln=True)

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "B. Profitabilitate & Eficienta", ln=True)
    pdf.set_font("Arial", '', 11)
    
    pdf.cell(63, 8, f"Marja Profit: {get_fmt('profitMargins', True)}", border=1)
    pdf.cell(63, 8, f"Marja Operationala: {get_fmt('operatingMargins', True)}", border=1)
    pdf.cell(63, 8, f"ROE (Return on Equity): {get_fmt('returnOnEquity', True)}", border=1, ln=True)
    pdf.cell(63, 8, f"Crestere Venituri: {get_fmt('revenueGrowth', True)}", border=1)
    pdf.cell(63, 8, f"Crestere Profit: {get_fmt('earningsGrowth', True)}", border=1)
    pdf.cell(63, 8, f"Gross Margins: {get_fmt('grossMargins', True)}", border=1, ln=True)

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "C. Bilant (Sanatate Financiara)", ln=True)
    pdf.set_font("Arial", '', 11)
    
    cash = info.get('totalCash', 0)
    debt = info.get('totalDebt', 0)
    
    pdf.cell(95, 8, f"Total Cash: ${cash/1e9:.1f} B", border=1)
    pdf.cell(95, 8, f"Datorie Totala: ${debt/1e9:.1f} B", border=1, ln=True)
    pdf.cell(95, 8, f"Current Ratio: {get_fmt('currentRatio')}", border=1)
    pdf.cell(95, 8, f"Cash per Share: {get_fmt('totalCashPerShare')}", border=1, ln=True)

    # 5. LISTA DE MOTIVE (SCORING)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "4. DETALII SCORING", ln=True, fill=True)
    pdf.set_font("Arial", '', 11)
    for r in reasons:
        pdf.cell(0, 8, f" -> {clean_text_for_pdf(r)}", ln=True)

    # Disclaimer
    pdf.ln(10)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5, "DISCLAIMER: Acest document este generat automat si nu reprezinta un sfat financiar. Informatiile sunt preluate din surse publice si pot contine erori. Investitiile la bursa implica riscuri.")

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SIDEBAR ---
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

if st.sidebar.button("➕ Salvează la Favorite"):
    ticker_to_add = st.session_state.active_ticker
    if ticker_to_add not in st.session_state.favorites:
        try:
            t_info = yf.Ticker(ticker_to_add).info
            long_name = t_info.get('longName', ticker_to_add)
            st.session_state.favorites.append(ticker_to_add)
            st.session_state.favorite_names[ticker_to_add] = long_name
            st.sidebar.success("Adăugat!")
            st.rerun()
        except Exception: 
            st.sidebar.error("Eroare!")

st.sidebar.subheader("Lista Mea")
if st.session_state.favorites:
    for fav in st.session_state.favorites:
        full_n = st.session_state.favorite_names.get(fav, fav)
        c1, c2 = st.sidebar.columns([4, 1])
        def set_fav(f=fav): st.session_state.active_ticker = f
        def del_fav(f=fav): st.session_state.favorites.remove(f)
        c1.button(f"{fav}", key=f"btn_{fav}", on_click=set_fav, help=full_n)
        c2.button("X", key=f"del_{fav}", on_click=del_fav)
else:
    st.sidebar.info("Nicio companie salvată.")

# --- MAIN APP ---
temp_stock = yf.Ticker(st.session_state.active_ticker)
try:
    temp_name = temp_stock.info.get('longName', st.session_state.active_ticker)
except:
    temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker}")
st.caption(f"{temp_name}")

# --- SLIDER MODIFICAT CU LISTA EXTINSA ---
optiuni_ani = ['1mo', '3mo', '6mo', '1y', '2y', '3y', '4y', '5y', '6y', '7y', '8y', '9y', '10y', 'max']
perioada = st.select_slider("Perioada:", options=optiuni_ani, value='1y')

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Analiză", "📈 Tehnic", "📅 Calendar", "📰 Știri", "💰 Dividende", "📋 Audit (PDF)", "⚔️ Vs"
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

    with tab2: 
        st.subheader("RSI Momentum")
        rsi_val = calculate_rsi(history['Close']).iloc[-1] # Calculam RSI aici sa il avem
        st.metric("RSI (14)", f"{rsi_val:.2f}")
        if rsi_val > 70: st.warning("Supra-cumparat (>70)")
        elif rsi_val < 30: st.success("Supra-vandut (<30)")
        
        st.markdown("---")
        st.subheader("Insider Trading")
        try:
            ins = stock.insider_transactions
            if ins is not None and not ins.empty:
                st.dataframe(ins.head(10)[['Start Date', 'Insider', 'Shares', 'Text']])
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
        dy = info.get('dividendYield', 0) or 0
        st.metric("Randament", f"{dy*100:.2f}%")
        if dy > 0:
            inv = st.number_input("Investitie ($)", 1000.0)
            st.success(f"Lunar: ${(inv*dy)/12:.2f}")

    with tab6: # PDF EXTINS
        st.write("Genereaza un raport complet cu toti indicatorii financiari.")
        if st.button("📄 Descarca Raport Complet"):
            try:
                # Recalculam RSI aici daca nu e disponibil
                curr_rsi = calculate_rsi(history['Close']).iloc[-1]
                risk_data = {'vol': volatility, 'dd': max_dd}
                
                # APELAM FUNCTIA EXTINSA CU TOATE DATELE
                pdf_bytes = create_extended_pdf(
                    ticker=st.session_state.active_ticker,
                    full_name=temp_name,
                    price=curr_price,
                    score=score,
                    reasons=reasons,
                    verdict=verdict,
                    risk=risk_data,
                    info=info,     # Trimitem tot dictionarul INFO
                    rsi_val=curr_rsi # Trimitem si RSI
                )
                
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Raport_Audit_{st.session_state.active_ticker}.pdf">📥 Descarca PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e: 
                st.error(f"Eroare generare PDF: {str(e)}")

    with tab7:
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
