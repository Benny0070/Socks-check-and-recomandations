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
    .stMetric { background-color: #262730; padding: 10px; border-radius: 5px; border-left: 5px solid #4CAF50; }
    h1, h2, h3 { color: #4CAF50 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- INIȚIALIZARE LISTĂ FAVORITE (SESSION STATE) ---
if 'favorites' not in st.session_state:
    st.session_state.favorites = []

# --- 2. FUNCȚII UTILITARE ---
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        # Cerem istoric pe 5 ani
        history = stock.history(period="5y")
        info = stock.info
        return stock, history, info
    except:
        return None, None, None

def calculate_prime_score(info, history):
    score = 0
    reasons = []
    
    # 1. Trend (Media 200 zile)
    if not history.empty:
        # Calculăm media mobilă simplă pe ultimele 200 de zile
        sma200 = history['Close'].rolling(window=200).mean().iloc[-1]
        current_price = history['Close'].iloc[-1]
        
        if current_price > sma200:
            score += 20
            reasons.append("Preț peste media de 200 zile (Trend Ascendent)")
    
    # 2. Profitabilitate (Marja Profit)
    profit_margin = info.get('profitMargins', 0)
    if profit_margin > 0.15: # 15%
        score += 20
        reasons.append(f"Marjă de profit solidă: {profit_margin*100:.1f}%")
        
    # 3. Creștere (Revenue Growth)
    rev_growth = info.get('revenueGrowth', 0)
    if rev_growth > 0.10: # 10%
        score += 20
        reasons.append(f"Creștere venituri: {rev_growth*100:.1f}%")
        
    # 4. Evaluare (P/E Ratio)
    pe_ratio = info.get('trailingPE', 0)
    if pe_ratio is None: pe_ratio = 0
    
    if 0 < pe_ratio < 40:
        score += 20
        reasons.append(f"P/E Ratio rezonabil: {pe_ratio:.2f}")
    elif pe_ratio > 40:
        score += 10
        reasons.append(f"P/E Ratio ridicat ({pe_ratio:.2f}), dar acceptabil pentru growth")

    # 5. Cash vs Datorii
    cash = info.get('totalCash', 0)
    debt = info.get('totalDebt', 0)
    # Protecție dacă datele sunt None
    if cash is None: cash = 0
    if debt is None: debt = 0
    
    if cash > debt:
        score += 20
        reasons.append("Bilanț Fortăreață (Cash > Datorii)")
        
    return score, reasons

def get_news_sentiment(stock):
    try:
        news = stock.news
        if not news:
            return "Neutru", []
        
        # FIX: Folosim .get() pentru a evita KeyError dacă 'title' lipsește
        headlines = [n.get('title', 'Stire fara titlu') for n in news[:5]]
        
        # Analiză rudimentară de sentiment pe baza cuvintelor cheie
        positive_keywords = ['beat', 'rise', 'jump', 'high', 'buy', 'growth', 'up', 'record', 'strong', 'surge']
        negative_keywords = ['miss', 'fall', 'drop', 'low', 'sell', 'weak', 'down', 'loss', 'crash', 'plunge']
        
        score = 0
        for h in headlines:
            h_lower = h.lower()
            if any(k in h_lower for k in positive_keywords):
                score += 1
            if any(k in h_lower for k in negative_keywords):
                score -= 1
                
        if score > 0: return "Pozitiv 🟢", headlines
        elif score < 0: return "Negativ 🔴", headlines
        else: return "Neutru ⚪", headlines
    except Exception as e:
        return "Indisponibil", [f"Eroare la preluarea știrilor: {e}"]

def create_audit_pdf(ticker, current_price, score, reasons, verdict, risk_data, info):
    pdf = FPDF()
    pdf.add_page()
    
    # Titlu
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Raport Audit PRIME: {ticker}", ln=True, align='C')
    pdf.ln(10)
    
    # Detalii Principale
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data Raport: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.cell(0, 10, f"Pret Actual: ${current_price:.2f}", ln=True)
    pdf.cell(0, 10, f"Scor PRIME: {score}/100", ln=True)
    pdf.cell(0, 10, f"Verdict Risc: {verdict}", ln=True)
    pdf.ln(10)
    
    # Motive Scor
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Analiza Factorilor:", ln=True)
    pdf.set_font("Arial", '', 12)
    for reason in reasons:
        # Curățăm textul de caractere speciale pentru PDF simplu
        clean_reason = reason.encode('latin-1', 'ignore').decode('latin-1')
        pdf.cell(0, 10, f"- {clean_reason}", ln=True)
    
    pdf.ln(10)
    
    # Date Risc
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Date de Risc (5 ani):", ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Randament Anual (CAGR): {risk_data['cagr']:.2f}%", ln=True)
    pdf.cell(0, 10, f"Volatilitate (Std Dev): {risk_data['volatility']:.2f}%", ln=True)
    pdf.cell(0, 10, f"Cadere Maxima (Drawdown): {risk_data['drawdown']:.2f}%", ln=True)
    
    # Disclaimer
    pdf.ln(20)
    pdf.set_font("Arial", 'I', 10)
    pdf.multi_cell(0, 10, "Acest raport este generat automat si nu reprezinta un sfat financiar. Investitiile implica riscuri.")
    
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SIDEBAR: CĂUTARE & WATCHLIST ---
st.sidebar.header("🔍 Control Panel")
ticker_input = st.sidebar.text_input("Simbol Bursier (ex: NVDA)", value="NVDA").upper()

# Adăugare la Favorite
if st.sidebar.button("➕ Adaugă la Favorite"):
    if ticker_input not in st.session_state.favorites:
        st.session_state.favorites.append(ticker_input)
        st.sidebar.success(f"{ticker_input} adăugat!")

# Afișare Listă Favorite
st.sidebar.markdown("---")
st.sidebar.header("⭐ Lista Favorite")
if st.session_state.favorites:
    for fav in st.session_state.favorites:
        col1, col2 = st.sidebar.columns([3, 1])
        col1.write(f"**{fav}**")
        if col2.button("❌", key=f"del_{fav}"):
            st.session_state.favorites.remove(fav)
            st.rerun()
else:
    st.sidebar.info("Lista e goală.")

# --- MAIN APP LOGIC ---
st.title("🛡️ PRIME Terminal v11.1")

# Tab-uri principale
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Analiză", "📰 Știri & Sentiment", "💰 Calculator Dividende", "📋 Audit Economic", "⚔️ Comparatie"])

if ticker_input:
    # Verificăm dacă utilizatorul a introdus ceva valid
    stock, history, info = get_stock_data(ticker_input)
    
    if stock and not history.empty:
        # Calcule Comune
        current_price = history['Close'].iloc[-1]
        score, reasons = calculate_prime_score(info, history)
        
        # Calcul Risc
        daily_ret = history['Close'].pct_change().dropna()
        # Calcul CAGR (Compound Annual Growth Rate)
        if len(history) > 0:
            cagr = ((history['Close'].iloc[-1] / history['Close'].iloc[0]) ** (1/5) - 1) * 100
        else:
            cagr = 0
            
        volatility = daily_ret.std() * np.sqrt(252) * 100
        max_drawdown = ((history['Close'] / history['Close'].cummax()) - 1).min() * 100
        sharpe = (cagr - 4) / volatility if volatility > 0 else 0
        
        # LOGICA VERDICTULUI (CONSERVATOR)
        if max_drawdown < -35: 
            verdict = "Risc Ridicat 🔴"
            verdict_desc = f"Istoricul arată scăderi mari (Max Drawdown: {max_drawdown:.2f}%). Potențial mare, dar volatil."
        elif sharpe > 1:
            verdict = "Investiție Echilibrată 🟢"
            verdict_desc = "Randament bun raportat la riscurile asumate."
        else:
            verdict = "Risc Mediu 🟡"
            verdict_desc = "Performanță medie cu volatilitate moderată."

        # --- TAB 1: ANALIZĂ ---
        with tab1:
            # Header
            col1, col2, col3 = st.columns(3)
            col1.metric("Preț Actual", f"${current_price:.2f}")
            col2.metric("Scor PRIME", f"{score}/100", help="Scor bazat pe: Trend, Profit, Creștere, P/E, Cash")
            col3.metric("Recomandare AI", verdict.split()[0] + " " + verdict.split()[1])

            # Grafic
            st.subheader("Evoluție Preț (5 Ani)")
            st.line_chart(history['Close'])
            
            # Detalii Scor
            with st.expander("⭐ Vezi de ce a primit acest scor"):
                for r in reasons:
                    st.write(f"✅ {r}")

        # --- TAB 2: ȘTIRI ---
        with tab2:
            st.subheader(f"Sentiment Piață: {ticker_input}")
            sentiment, headlines = get_news_sentiment(stock)
            st.markdown(f"### Stare Generală: {sentiment}")
            if headlines:
                for h in headlines:
                    st.markdown(f"- {h}")
            else:
                st.info("Nu s-au găsit știri recente.")

        # --- TAB 3: DIVIDENDE ---
        with tab3:
            st.subheader("Calculator Venit Pasiv")
            div_yield = info.get('dividendYield', 0)
            
            if div_yield and div_yield > 0:
                st.metric("Randament Dividend", f"{div_yield*100:.2f}%")
                investitie = st.number_input("Suma Investită ($)", value=10000, step=1000)
                
                venit_anual = investitie * div_yield
                venit_lunar = venit_anual / 12
                # Proiectie 10 ani (fara reinvestire pt simplicitate)
                venit_10_ani = venit_anual * 10 
                
                c1, c2 = st.columns(2)
                c1.metric("Venit Lunar Estimat", f"${venit_lunar:.2f}")
                c2.metric("Venit pe 10 Ani", f"${venit_10_ani:.2f}")
                
                st.info(f"Pentru a primi $1,000/lună, ai nevoie de o investiție de aprox. ${12000/div_yield:,.0f}")
            else:
                st.warning("Această companie NU plătește dividende (sau datele lipsesc).")

        # --- TAB 4: AUDIT PDF ---
        with tab4:
            st.subheader("Generează Raport PDF")
            st.write("Selectează ce vrei să incluzi în raport:")
            inc_score = st.checkbox("Scor PRIME și Motive", value=True)
            inc_risk = st.checkbox("Analiza de Risc (Drawdown, Volatilitate)", value=True)
            
            if st.button("Descarcă Raport PDF"):
                risk_data = {"cagr": cagr, "volatility": volatility, "drawdown": max_drawdown}
                try:
                    pdf_bytes = create_audit_pdf(ticker_input, current_price, score, reasons, verdict, risk_data, info)
                    b64 = base64.b64encode(pdf_bytes).decode()
                    href = f'<a href="data:application/octet-stream;base64,{b64}" download="Audit_{ticker_input}.pdf">📥 Descarcă Auditul {ticker_input}</a>'
                    st.markdown(href, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Eroare la generarea PDF: {e}")

    else:
        st.error("Simbol invalid sau date lipsă. Încearcă alt ticker.")

# --- TAB 5: COMPARATIE ---
with tab5:
    st.header("⚔️ Arena Companiilor")
    
    if not st.session_state.favorites:
        st.info("Adaugă companii la Favorite (din Sidebar) pentru a le putea compara aici!")
    else:
        # Multiselect pentru a alege ce comparăm
        comp_tickers = st.multiselect("Alege companiile pentru comparație:", st.session_state.favorites, default=st.session_state.favorites[:2] if len(st.session_state.favorites) >=2 else st.session_state.favorites)
        
        if comp_tickers:
            st.write("Se încarcă datele...")
            try:
                # Descărcăm datele pentru toate
                comp_data = yf.download(comp_tickers, period="1y")['Adj Close']
                
                # Normalizare: Toate încep de la 0%
                if not comp_data.empty:
                    normalized_data = (comp_data / comp_data.iloc[0] - 1) * 100
                    
                    st.subheader("Performanță Relativă (%) - Ultimul An")
                    st.line_chart(normalized_data)
                    
                    # Tabel cu cifrele finale
                    st.write("#### Randament total în ultimul an:")
                    final_returns = normalized_data.iloc[-1].sort_values(ascending=False)
                    for t, ret in final_returns.items():
                        color = "green" if ret > 0 else "red"
                        st.markdown(f"**{t}**: :{color}[{ret:.2f}%]")
                else:
                    st.warning("Nu există date suficiente pentru comparație.")
                    
            except Exception as e:
                st.error(f"Eroare la preluarea datelor pentru comparație: {e}")
