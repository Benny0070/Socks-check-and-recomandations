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
if 'favorites' not in st.session_state:
    st.session_state.favorites = [] # Lista de tickere
if 'favorite_names' not in st.session_state:
    st.session_state.favorite_names = {} # Dict pentru nume complete {Ticker: Nume}
if 'active_ticker' not in st.session_state:
    st.session_state.active_ticker = "NVDA"

# --- 2. FUNCȚII UTILITARE ---

def clean_text_for_pdf(text):
    text = str(text)
    text = text.replace("🔴", "[ROSU]").replace("🟢", "[VERDE]").replace("🟡", "[GALBEN]").replace("⚪", "[NEUTRU]")
    return text.encode('latin-1', 'ignore').decode('latin-1')

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
        sma = history['Close'].mean() # Media pe perioada selectată
        current = history['Close'].iloc[-1]
        if current > sma:
            score += 20
            reasons.append("Trend Ascendent (Pret peste media perioadei)")
    
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
        reasons.append(f"P/E Ratio Atractiv: {pe:.2f}")
    
    # 5. Cash
    cash = info.get('totalCash', 0) or 0
    debt = info.get('totalDebt', 0) or 0
    if cash > debt:
        score += 20
        reasons.append("Cash > Datorii (Bilant Puternic)")
        
    return score, reasons

def get_news_sentiment(stock):
    try:
        news = stock.news
        headlines = []
        if news:
            for n in news[:5]:
                t = n.get('title', '')
                if t and t not in headlines: headlines.append(t)
        
        if not headlines: return "Neutru", ["Nu există știri recente."]
        
        # Analiza simplă
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
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"AUDIT: {ticker} - {clean_text_for_pdf(full_name)}", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data: {datetime.now().strftime('%d-%m-%Y')} | Pret: ${price:.2f}", ln=True)
    pdf.cell(0, 10, f"Scor PRIME: {score}/100 | Verdict: {clean_text_for_pdf(verdict)}", ln=True)
    pdf.ln(5)

    # 1. Indicatori Extinși
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "1. Indicatori Financiari Detaliati", ln=True)
    pdf.set_font("Arial", '', 11)
    
    # Extragere date
    roe = info.get('returnOnEquity', 0) or 0
    roa = info.get('returnOnAssets', 0) or 0
    curr_ratio = info.get('currentRatio', 0) or 0
    beta = info.get('beta', 0) or 0
    debt_eq = info.get('debtToEquity', 0) or 0
    
    # Interpretare
    def interpret(val, threshold, type='high'):
        if type == 'high': return "Bun" if val > threshold else "Slab"
        return "Bun" if val < threshold else "Riscant"

    lines = [
        f"ROE (Randament Capital): {roe*100:.2f}% -> {'Excelent' if roe > 0.15 else 'Mediu'}",
        f"ROA (Randament Active): {roa*100:.2f}% -> {'Bun' if roa > 0.05 else 'Slab'}",
        f"Current Ratio (Lichiditate): {curr_ratio:.2f} -> {'Sigur (>1.5)' if curr_ratio > 1.5 else 'Atentie (<1.5)'}",
        f"Beta (Volatilitate): {beta:.2f} -> {'Stabil (<1)' if beta < 1 else 'Volatil (>1)'}",
        f"Datorie/Capital (Debt/Eq): {debt_eq:.2f} -> {'Conservator' if debt_eq < 100 else 'Levier Mare'}"
    ]
    
    for l in lines:
        pdf.cell(0, 8, f"- {clean_text_for_pdf(l)}", ln=True)
    pdf.ln(5)

    # 2. Factori Scor
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "2. Analiza PRIME (Motive Scor)", ln=True)
    pdf.set_font("Arial", '', 11)
    for r in reasons:
        pdf.cell(0, 8, f"- {clean_text_for_pdf(r)}", ln=True)
    pdf.ln(5)
    
    # 3. Risc
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "3. Analiza de Risc", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 8, f"Volatilitate Anuala: {risk['vol']:.2f}%", ln=True)
    pdf.cell(0, 8, f"Cadere Maxima (Drawdown): {risk['dd']:.2f}%", ln=True)

    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SIDEBAR ---
st.sidebar.header("🔍 Control Panel")

# Căutare
search_ticker = st.sidebar.text_input("Simbol (ex: TSLA)", value=st.session_state.active_ticker).upper()

# Buton Adăugare + Fetch Nume
if st.sidebar.button("➕ Adaugă la Favorite"):
    if search_ticker not in st.session_state.favorites:
        try:
            # Luăm numele real
            t_info = yf.Ticker(search_ticker).info
            long_name = t_info.get('longName', search_ticker)
            # Salvăm
            st.session_state.favorites.append(search_ticker)
            st.session_state.favorite_names[search_ticker] = long_name
            st.sidebar.success("Adăugat!")
        except:
            st.sidebar.error("Simbol invalid!")

st.sidebar.markdown("---")
st.sidebar.subheader("Lista Mea")

# Lista Favorite (Fără iconițe folder)
if st.session_state.favorites:
    for fav in st.session_state.favorites:
        full_n = st.session_state.favorite_names.get(fav, fav)
        # Scurtăm numele dacă e prea lung
        disp_name = (full_n[:20] + '..') if len(full_n) > 20 else full_n
        
        c1, c2 = st.sidebar.columns([4, 1])
        if c1.button(f"{fav} | {disp_name}", key=f"btn_{fav}"):
            st.session_state.active_ticker = fav
            st.rerun()
        if c2.button("X", key=f"del_{fav}"):
            st.session_state.favorites.remove(fav)
            st.rerun()
else:
    st.sidebar.info("Nicio companie salvată.")

# --- MAIN APP ---
# Fetch date pentru titlu
temp_stock = yf.Ticker(st.session_state.active_ticker)
try:
    temp_name = temp_stock.info.get('longName', st.session_state.active_ticker)
except:
    temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker} - {temp_name}")

# SELECTOR PERIOADA
perioada = st.select_slider(
    "Selectează Perioada Graficului:",
    options=['1mo', '3mo', '6mo', '1y', '2y', '5y', 'max'],
    value='1y'
)

# Tab-uri
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Analiză", "📰 Știri", "💰 Dividende", "📋 Audit PDF", "⚔️ Comparație"])

stock, history, info = get_stock_data(st.session_state.active_ticker, period=perioada)

if stock and not history.empty:
    curr_price = history['Close'].iloc[-1]
    
    # Calcule Risc/Scor
    daily_ret = history['Close'].pct_change().dropna()
    volatility = daily_ret.std() * np.sqrt(252) * 100
    max_dd = ((history['Close'] / history['Close'].cummax()) - 1).min() * 100
    score, reasons = calculate_prime_score(info, history)
    
    # Verdict
    if max_dd < -35: 
        verdict = "Risc Ridicat 🔴"
        style = "error"
    elif score > 75: 
        verdict = "Oportunitate 🟢"
        style = "success"
    else: 
        verdict = "Neutru 🟡"
        style = "warning"

    # TAB 1: ANALIZĂ
    with tab1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Preț Actual", f"${curr_price:.2f}")
        c2.metric("Scor PRIME", f"{score}/100")
        c3.metric("Risc (Volatilitate)", f"{volatility:.1f}%")
        
        if style == "success": st.success(f"Verdict: {verdict}")
        elif style == "warning": st.warning(f"Verdict: {verdict}")
        else: st.error(f"Verdict: {verdict}")
        
        st.line_chart(history['Close'])

    # TAB 2: ȘTIRI
    with tab2:
        s, heads = get_news_sentiment(stock)
        st.write(f"Sentiment: **{s}**")
        for h in heads: st.markdown(f"- {h}")

    # TAB 3: DIVIDENDE (Flexibil)
    with tab3:
        dy = info.get('dividendYield', 0) or 0
        if dy > 0:
            st.metric("Randament Anual", f"{dy*100:.2f}%")
            # Input liber (float)
            invest = st.number_input("Suma Investită ($)", value=1000.0, step=50.0, format="%.2f")
            
            anual = invest * dy
            lunar = anual / 12
            st.success(f"Venit Lunar Estimat: **${lunar:.2f}**")
            st.info(f"Venit Anual: ${anual:.2f}")
        else:
            st.warning("Nu oferă dividende.")

    # TAB 4: PDF (Extins)
    with tab4:
        st.write("Generează raport detaliat (Indicatori + Interpretare).")
        if st.button("Descarcă Raport PRO"):
            try:
                risk_data = {'vol': volatility, 'dd': max_dd}
                pdf_bytes = create_extended_pdf(
                    st.session_state.active_ticker, temp_name, curr_price,
                    score, reasons, verdict, risk_data, info
                )
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/octet-stream;base64,{b64}" download="Audit_{st.session_state.active_ticker}.pdf">📥 Descarcă PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Eroare: {e}")

    # TAB 5: COMPARATIE (Procentuală)
    with tab5:
        st.header("Analiză Comparativă")
        if len(st.session_state.favorites) < 2:
            st.info("Adaugă cel puțin 2 companii la Favorite.")
        else:
            sel = st.multiselect("Selectează:", st.session_state.favorites, default=st.session_state.favorites[:2])
            if sel:
                st.write("Se calculează diferențele...")
                df_comp = pd.DataFrame()
                
                # Fetch date
                for t in sel:
                    h = yf.Ticker(t).history(period="1y")['Close']
                    if not h.empty:
                        # Normalizare la %
                        df_comp[t] = (h / h.iloc[0] - 1) * 100
                
                if not df_comp.empty:
                    st.line_chart(df_comp)
                    
                    # Analiză text
                    final_vals = df_comp.iloc[-1].sort_values(ascending=False)
                    best = final_vals.index[0]
                    worst = final_vals.index[-1]
                    diff = final_vals[best] - final_vals[worst]
                    
                    st.markdown(f"### 🏆 Liderul este **{best}**")
                    st.markdown(f"Are un randament cu **{diff:.2f}%** mai mare decât {worst} în ultimul an.")
                    
                    st.write("#### Clasament Detaliat (1 An):")
                    for tick, val in final_vals.items():
                        c = "green" if val > 0 else "red"
                        # Luăm numele complet pentru claritate
                        f_name = st.session_state.favorite_names.get(tick, tick)
                        st.markdown(f"**{f_name} ({tick})**: :{c}[{val:.2f}%]")

else:
    st.error("Date indisponibile pentru acest simbol.")
