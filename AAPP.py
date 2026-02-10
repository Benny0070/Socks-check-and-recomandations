import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from fpdf import FPDF
import base64
from datetime import datetime
import json
import os

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
        # Citim parola de acces din Secrets
        secret_access = st.secrets.get("ACCESS_PASSWORD", "1234") 
        
        if password_input == secret_access:
            st.session_state['access_granted'] = True
            st.rerun()
        else:
            st.error("⛔ Parolă de acces greșită.")

    return False

# DACA NU E LOGAT, OPRIM TOTUL AICI
if not check_access_password():
    st.stop()

# =========================================================
# AICI ÎNCEPE APLICAȚIA (DOAR DUPĂ LOGIN)
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
def clean_text_for_pdf(text):
    text = str(text)
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
    if not history.empty:
        sma = history['Close'].mean() 
        current = history['Close'].iloc[-1]
        if current > sma:
            score += 20
            reasons.append("Trend Ascendent")
    pm = info.get('profitMargins', 0) or 0
    if pm > 0.15: 
        score += 20
        reasons.append(f"Marja Profit: {pm*100:.1f}%")
    rg = info.get('revenueGrowth', 0) or 0
    if rg > 0.10: 
        score += 20
        reasons.append(f"Crestere Venituri: {rg*100:.1f}%")
    pe = info.get('trailingPE', 0) or 0
    if 0 < pe < 40:
        score += 20
        reasons.append(f"Evaluare Corecta (P/E: {pe:.2f})")
    cash = info.get('totalCash', 0) or 0
    debt = info.get('totalDebt', 0) or 0
    if cash > debt:
        score += 20
        reasons.append("Bilant Puternic")
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

def create_extended_pdf(ticker, full_name, price, score, reasons, verdict, risk, info, rsi_val):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(0, 15, f"RAPORT DE AUDIT: {ticker}", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Generat la: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(5)

    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "1. REZUMAT EXECUTIV", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", '', 12)
    pdf.cell(50, 10, f"Companie: {clean_text_for_pdf(full_name)}", ln=True)
    pdf.cell(50, 10, f"Pret Curent: ${price:.2f}", ln=True)
    pdf.cell(50, 10, f"Scor PRIME: {score}/100", ln=True)
    pdf.cell(50, 10, f"Verdict: {clean_text_for_pdf(verdict)}", ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "2. PROFIL DE RISC & TEHNIC", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("Arial", '', 11)
    rsi_interp = "Supra-cumparat (Scump)" if rsi_val > 70 else "Supra-vandut (Ieftin)" if rsi_val < 30 else "Neutru"
    pdf.cell(95, 8, f"Volatilitate: {risk['vol']:.1f}%", border=1)
    pdf.cell(95, 8, f"Max Drawdown: {risk['dd']:.1f}%", border=1, ln=True)
    pdf.cell(95, 8, f"RSI (14): {rsi_val:.2f}", border=1)
    pdf.cell(95, 8, f"Semnal RSI: {rsi_interp}", border=1, ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "3. INDICATORI FUNDAMENTALI", ln=True, fill=True)
    pdf.ln(2)
    def get_fmt(key, is_perc=False):
        val = info.get(key)
        if val is None: return "N/A"
        if is_perc: return f"{val*100:.2f}%"
        return f"{val:.2f}"
    
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "A. Evaluare", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(63, 8, f"P/E Ratio: {get_fmt('trailingPE')}", border=1)
    pdf.cell(63, 8, f"Forward P/E: {get_fmt('forwardPE')}", border=1)
    pdf.cell(63, 8, f"PEG Ratio: {get_fmt('pegRatio')}", border=1, ln=True)
    pdf.cell(63, 8, f"EV: {info.get('enterpriseValue', 0)/1e9:.1f}B", border=1, ln=True)

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "B. Profitabilitate", ln=True)
    pdf.set_font("Arial", '', 11)
    pdf.cell(63, 8, f"Marja Profit: {get_fmt('profitMargins', True)}", border=1)
    pdf.cell(63, 8, f"Marja Ops: {get_fmt('operatingMargins', True)}", border=1)
    pdf.cell(63, 8, f"Crestere Venit: {get_fmt('revenueGrowth', True)}", border=1, ln=True)

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 8, "C. Bilant", ln=True)
    pdf.set_font("Arial", '', 11)
    cash = info.get('totalCash', 0)
    debt = info.get('totalDebt', 0)
    pdf.cell(95, 8, f"Total Cash: ${cash/1e9:.1f} B", border=1)
    pdf.cell(95, 8, f"Datorie Totala: ${debt/1e9:.1f} B", border=1, ln=True)

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "4. MOTIVE SCOR", ln=True, fill=True)
    pdf.set_font("Arial", '', 11)
    for r in reasons: pdf.cell(0, 8, f" -> {clean_text_for_pdf(r)}", ln=True)

    pdf.ln(10)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5, "DISCLAIMER: Generat automat. Nu este sfat financiar.")
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

# =========================================================
# NIVEL 2: SECURITATE LA EDITARE (ADMIN ONLY)
# =========================================================

st.sidebar.caption("🔧 Zonă Administrator")
# Câmpul pentru parola de ADMIN (separat de cea de acces)
admin_input = st.sidebar.text_input("Parola Editare", type="password", placeholder="Pentru a modifica lista...")
secret_admin_key = st.secrets.get("ADMIN_PASSWORD", "admin_secret")

# Verificăm dacă parola introdusă este cea de Admin
IS_ADMIN = (admin_input == secret_admin_key)

if IS_ADMIN:
    st.sidebar.success("✅ Mod Editare Activ")
    
    # 1. Buton ADAUGĂ (Doar dacă ești Admin)
    if st.sidebar.button("➕ Adaugă la Favorite"):
        ticker_to_add = st.session_state.active_ticker
        if ticker_to_add not in st.session_state.favorites:
            try:
                t_info = yf.Ticker(ticker_to_add).info
                long_name = t_info.get('longName', ticker_to_add)
                st.session_state.favorites.append(ticker_to_add)
                st.session_state.favorite_names[ticker_to_add] = long_name
                save_db(st.session_state.favorites, st.session_state.favorite_names)
                st.sidebar.success("Salvat!")
                st.rerun()
            except Exception: st.sidebar.error("Eroare!")
else:
    # Dacă nu ești Admin, vezi doar un mesaj informativ
    if st.session_state.active_ticker not in st.session_state.favorites:
        st.sidebar.info("🔒 Loghează-te ca Admin pentru a adăuga.")

st.sidebar.subheader("Lista Mea")

# Afișare Lista
if st.session_state.favorites:
    for fav in st.session_state.favorites:
        full_n = st.session_state.favorite_names.get(fav, fav)
        
        # Admin vede coloana cu butonul X
        if IS_ADMIN:
            c1, c2 = st.sidebar.columns([4, 1])
        else:
            c1 = st.sidebar # Vizitatorul vede doar numele
        
        def set_fav(f=fav): st.session_state.active_ticker = f
        def del_fav(f=fav): 
            st.session_state.favorites.remove(f)
            save_db(st.session_state.favorites, st.session_state.favorite_names)

        # Toată lumea poate da click pe nume să încarce
        if IS_ADMIN:
            c1.button(f"{fav}", key=f"btn_{fav}", on_click=set_fav, help=full_n)
            # 2. Buton STERGE (Doar dacă ești Admin)
            c2.button("X", key=f"del_{fav}", on_click=del_fav) 
        else:
            st.sidebar.button(f"{fav}", key=f"btn_{fav}", on_click=set_fav, help=full_n)
else:
    st.sidebar.info("Lista este goală.")

# Buton Logout General (Iese de tot din site)
st.sidebar.markdown("---")
if st.sidebar.button("🔒 Logout Site"):
    st.session_state['access_granted'] = False
    st.rerun()

# --- MAIN APP (PUBLIC DUPA ACCES) ---
temp_stock = yf.Ticker(st.session_state.active_ticker)
try: temp_name = temp_stock.info.get('longName', st.session_state.active_ticker)
except: temp_name = st.session_state.active_ticker

st.title(f"🛡️ {st.session_state.active_ticker}")
st.caption(f"{temp_name}")

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

# --- TAB 5: DIVIDENDE ---
    with tab5:
        dy = info.get('dividendYield', 0) or 0
        st.metric("Randament Dividend", f"{dy*100:.2f}%")
        
        if dy > 0:
            # Aici am pus min_value=1.0 (ca să nu poți băga 0 sau minus)
            inv = st.number_input("Investiție Simulată ($)", min_value=1.0, value=100.0, step=10.0)
            
            lunar = (inv * dy) / 12
            anual = inv * dy
            
            st.success(f"💰 Dacă investești ${inv}, "primești aprox:" ${lunar:.2f} / lună (${anual:.2f} / an)")
        else:
            st.info("Această companie nu plătește dividende (sau nu avem date).")

    # --- TAB 6: RAPORT (Acum este aliniat corect SUB tab5, nu în el) ---
    with tab6:
        st.write("Genereaza un raport complet.")
        if st.button("📄 Descarca Raport Complet"):
            try:
                curr_rsi = calculate_rsi(history['Close']).iloc[-1]
                risk_data = {'vol': volatility, 'dd': max_dd}
                
                # Asigură-te că ai importat base64 la începutul fișierului
                import base64 
                
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

    # --- TAB 7: FAVORITE (Aliniat corect) ---
    with tab7:
        if len(st.session_state.favorites) >= 2:
            sel = st.multiselect("Alege:", st.session_state.favorites, default=st.session_state.favorites[:2])
            if sel:
                df = pd.DataFrame()
                for t in sel:
                    # Folosim un try-except și aici pentru siguranță
                    try:
                        h = yf.Ticker(t).history(period="1y")['Close']
                        if not h.empty: 
                            df[t] = (h/h.iloc[0]-1)*100
                    except:
                        pass
                st.line_chart(df)
        else: 
            st.info("Adauga minim 2 favorite pt comparație.")

# --- FINAL ELSE (Acesta trebuie să fie aliniat cu IF-ul principal de la începutul codului tău) ---
else:
    st.error(f"Nu am găsit date pentru {st.session_state.active_ticker}. Verifică simbolul.")
