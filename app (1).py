import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import json

# ══════════════════════════════════════════════════════════
# 1. 技術指標數學公式 (自寫版，確保不需依賴額外套件)
# ══════════════════════════════════════════════════════════

def compute_indicators(df):
    try:
        # RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # KD (9, 3, 3)
        low_min = df['Low'].rolling(window=9).min()
        high_max = df['High'].rolling(window=9).max()
        rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()

        # MACD (12, 26, 9)
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = exp1 - exp2
        df['DEM'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['DEM']

        # 布林通道 (20, 2)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD'] = df['Close'].rolling(window=20).std()
        df['Upper'] = df['MA20'] + (df['STD'] * 2)
        df['Lower'] = df['MA20'] - (df['STD'] * 2)
        return df
    except:
        return df

# ══════════════════════════════════════════════════════════
# 2. 數據抓取與 AI 邏輯
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def get_stock_data(code):
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{code}{suffix}")
            df = ticker.history(period="6mo", auto_adjust=True)
            if not df.empty and len(df) > 30:
                return compute_indicators(df)
        except: continue
    return None

def analyze_stock(df, metrics):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    scores = []
    
    if "KD" in metrics:
        scores.append(90 if last['K'] < 25 and last['K'] > prev['K'] else 10 if last['K'] > 75 and last['K'] < prev['K'] else 50)
    if "RSI" in metrics:
        scores.append(85 if last['RSI'] < 30 else 15 if last['RSI'] > 70 else 50)
    if "MACD" in metrics:
        scores.append(95 if last['OSC'] > 0 and prev['OSC'] <= 0 else 50)
    if "布林通道" in metrics:
        scores.append(90 if last['Close'] > last['Upper'] else 10 if last['Close'] < last['Lower'] else 50)
    if "成交量" in metrics:
        v_ma = df['Volume'].tail(5).mean()
        scores.append(90 if last['Volume'] > v_ma * 1.5 and last['Close'] > prev['Close'] else 50)

    score = int(sum(scores) / len(scores)) if scores else 50
    color = "#ef4444" if score >= 70 else "#22c55e" if score <= 30 else "#94a3b8"
    
    advice = "⚖️ 指標震盪，建議靜待方向突破"
    if score >= 70:
        advice = "🔥 趨勢偏多建議續抱" if last['Close'] > last['MA20'] else "🚀 殺低後站回，趨勢偏多建議續抱"
    elif score <= 30:
        advice = "📉 趨勢轉弱建議減碼" if last['Close'] < last['MA20'] else "⚠️ 殺低後雖站回，上方有壓建議見好就收"
        
    return score, advice, color, last

# ══════════════════════════════════════════════════════════
# 3. 介面與顯示
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 決策監控", layout="centered")

# 設定深色背景 CSS
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .card { background:#111827; padding:20px; border-radius:15px; border-left:6px solid #38bdf8; margin-bottom:15px; position: relative; }
</style>
""", unsafe_allow_html=True)

# 初始化 Session State (確保預設股票存在)
if "watchlist" not in st.session_state:
    st.session_state.watchlist = [
        {"id": "2330", "name": "台積電"}, 
        {"id": "2317", "name": "鴻海"},
        {"id": "00631L", "name": "元大台灣50正2"}
    ]

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 決策與監控設定")
    m_list = st.multiselect("啟用分析指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時漲跌預警 (%)", 0.5, 5.0, 2.0)
    st.divider()
    if st.button("🔄 重置為預設清單"):
        st.session_state.watchlist = [{"id": "2330", "name": "台積電"}, {"id": "2317", "name": "鴻海"}]
        st.rerun()

st.title("📈 台股 AI 決策監控系統")

# --- 補回：新增關注股票的功能區域 ---
with st.expander("➕ 新增關注股票", expanded=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入股票代碼 (例: 2454)", key="add_input").strip().upper()
    with c2:
        if st.button("加入監控"):
            if new_id and not any(s['id'] == new_id for s in st.session_state.watchlist):
                st.session_state.watchlist.append({"id": new_id, "name": new_id})
                st.rerun()

st.divider()

# 顯示股票卡片
for idx, s in enumerate(st.session_state.watchlist):
    df = get_stock_data(s['id'])
    if df is not None:
        score, advice, color, last = analyze_stock(df, m_list)
        chg = ((last['Close'] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100)
        
        # 繪製美化卡片
        st.markdown(f"""
        <div class="card" style="border-left-color: {color};">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:52px; height:52px; display:flex; align-items:center; justify-content:center;">
                {score}
            </div>
            <div style="font-size: 1.1rem; font-weight: bold; margin-bottom: 5px;">
                {s['name']} <span style="color:#64748b; font-size:0.8rem;">({s['id']})</span> {"🚨" if abs(chg)>=warn_p else ""}
            </div>
            <div style="font-size: 1.8rem; font-weight: 900; color: {color};">
                {last['Close']:.2f} <span style="font-size: 0.9rem;">({chg:+.2f}%)</span>
            </div>
            <div style="margin-top: 12px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px; font-size: 0.9rem;">
                <b style="color: {color}">💡 AI 決策建議：</b><br>{advice}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 移除按鈕 (放在卡片下方)
        if st.button(f"🗑️ 移除 {s['id']}", key=f"del_{idx}"):
            st.session_state.watchlist.pop(idx)
            st.rerun()
    else:
        st.error(f"❌ 無法讀取 {s['id']} 的資料，請確認代碼是否正確。")

# 自動每分鐘更新
time.sleep(60)
st.rerun()
