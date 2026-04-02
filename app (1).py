import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# ══════════════════════════════════════════════════════════
# 1. 核心指標運算 (自寫版，不依賴外掛套件)
# ══════════════════════════════════════════════════════════
def compute_indicators(df):
    try:
        df = df.copy()
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        # KD
        low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = exp1 - exp2
        df['DEM'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['DEM']
        # 布林通道
        df['MA20'] = df['Close'].rolling(20).mean()
        df['STD'] = df['Close'].rolling(20).std()
        df['Upper'] = df['MA20'] + (df['STD'] * 2)
        df['Lower'] = df['MA20'] - (df['STD'] * 2)
        return df
    except: return df

# ══════════════════════════════════════════════════════════
# 2. 強化版數據抓取 (解決載入失敗問題)
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def fetch_stock(code):
    """嘗試多種後綴並抓取中文名"""
    for sfx in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{code}{sfx}")
            # 使用較短的 period 提高成功率
            df = ticker.history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty and len(df) > 10:
                # 抓取中文名稱
                raw_name = ticker.info.get('longName', code)
                # 簡單中文判斷
                disp_name = raw_name if any(ord(c) > 127 for c in raw_name) else f"股票 {code}"
                return compute_indicators(df), disp_name
        except: continue
    return None, None

# ══════════════════════════════════════════════════════════
# 3. 介面與持久化儲存
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 智能監控", layout="centered")

# 預設五檔股票
DEFAULT_STOCKS = "2330,2317,00631L,2454,2603"

# 初始化清單
if "watchlist" not in st.session_state:
    # 優先從網址讀取
    params = st.query_params.get("wl", "")
    if params:
        st.session_state.watchlist = params.split(",")
    else:
        st.session_state.watchlist = DEFAULT_STOCKS.split(",")

def save_list():
    st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("📊 台股 AI 決策監控系統")

# --- 新增功能區 ---
with st.expander("➕ 新增關注股票", expanded=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入代碼 (例: 0050)", placeholder="請輸入 4-6 位數代碼").strip().upper()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                save_list()
                st.rerun()

st.divider()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 參數設定")
    warn_p = st.slider("漲跌預警門檻 (%)", 0.5, 5.0, 2.0)
    if st.button("🔄 重置為預設清單"):
        st.session_state.watchlist = DEFAULT_STOCKS.split(",")
        save_list()
        st.rerun()

# --- 顯示股票卡片 ---
for idx, code in enumerate(st.session_state.watchlist):
    df, c_name = fetch_stock(code)
    
    if df is not None:
        last, prev = df.iloc[-1], df.iloc[-2]
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        
        # 簡易評分邏輯
        score = 50
        if last['K'] < 30: score += 20
        if last['OSC'] > 0: score += 15
        if last['Close'] > last['MA20']: score += 15
        
        color = "#ef4444" if score >= 70 else "#22c55e" if score <= 30 else "#94a3b8"
        
        st.markdown(f"""
        <div style="background:#111827; padding:20px; border-radius:15px; border-left:6px solid {color}; margin-bottom:10px; color:white;">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size: 1.1rem; font-weight: bold;">{c_name} ({code}) {"🚨" if abs(chg)>=warn_p else ""}</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: {color};">{last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            save_list()
            st.rerun()
    else:
        st.error(f"❌ 代碼 {code} 讀取失敗，Yahoo 伺服器目前忙碌中，請稍後幾秒重新整理。")

# 每分鐘自動刷新
time.sleep(60)
st.rerun()
