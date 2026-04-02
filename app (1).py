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
# 2. 數據抓取與中文名稱獲取
# ══════════════════════════════════════════════════════════

def get_stock_info(code):
    """獲取中文名稱與歷史數據"""
    for suffix in [".TW", ".TWO"]:
        try:
            ticker = yf.Ticker(f"{code}{suffix}")
            df = ticker.history(period="6mo", auto_adjust=True)
            if not df.empty and len(df) > 30:
                # 嘗試獲取中文名稱
                name = ticker.info.get('longName', code)
                # 針對台灣券商名稱編碼修正 (若為英文則保留代碼)
                if any(ord(char) > 127 for char in name): 
                    display_name = name
                else:
                    display_name = f"股票 {code}"
                return compute_indicators(df), display_name
        except: continue
    return None, code

# ══════════════════════════════════════════════════════════
# 3. 介面與持久化邏輯
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 決策監控", layout="centered")

# CSS 美化
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:15px; border-left:6px solid #38bdf8; margin-bottom:15px; }
</style>
""", unsafe_allow_html=True)

# ─── 持久化處理：從 URL 讀取清單 ───
DEFAULT_LIST = ["2330", "2317", "00631L", "2454", "2603"]

if "watchlist" not in st.session_state:
    # 嘗試從 URL 參數獲取 (格式: ?wl=2330,2317)
    params = st.query_params.get("wl", "")
    if params:
        st.session_state.watchlist = params.split(",")
    else:
        st.session_state.watchlist = DEFAULT_LIST

def update_url():
    """同步清單到 URL 參數"""
    st.query_params["wl"] = ",".join(st.session_state.watchlist)

# ─── 側邊欄設定 ───
with st.sidebar:
    st.header("⚙️ 決策設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時漲跌預警 (%)", 0.5, 5.0, 2.0)
    if st.button("🔄 回復預設五檔"):
        st.session_state.watchlist = DEFAULT_LIST
        update_url()
        st.rerun()

st.title("📈 台股 AI 決策監控系統")

# ─── 新增股票功能 ───
with st.expander("➕ 新增關注股票", expanded=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入台股代碼", placeholder="例如: 2330").strip().upper()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                update_url()
                st.rerun()

st.divider()

# ─── 渲染股票列表 ───
for idx, code in enumerate(st.session_state.watchlist):
    df, c_name = get_stock_info(code)
    
    if df is not None:
        # AI 分析邏輯
        last = df.iloc[-1]
        prev = df.iloc[-2]
        scores = []
        if "KD" in m_list: scores.append(90 if last['K'] < 25 and last['K'] > prev['K'] else 10 if last['K'] > 75 and last['K'] < prev['K'] else 50)
        if "RSI" in m_list: scores.append(85 if last['RSI'] < 30 else 15 if last['RSI'] > 70 else 50)
        if "布林通道" in m_list: scores.append(90 if last['Close'] > last['Upper'] else 10 if last['Close'] < last['Lower'] else 50)
        
        score = int(sum(scores)/len(scores)) if scores else 50
        color = "#ef4444" if score >= 70 else "#22c55e" if score <= 30 else "#94a3b8"
        chg = ((last['Close'] - prev['Close']) / prev['Close'] * 100)
        
        st.markdown(f"""
        <div class="card" style="border-left-color: {color};">
            <div style="float:right; font-size:22px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size: 1.1rem; font-weight: bold;">{c_name} <span style="color:#64748b; font-size:0.8rem;">({code})</span> {"🚨" if abs(chg)>=warn_p else ""}</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: {color};">{last['Close']:.2f} <span style="font-size: 0.9rem;">({chg:+.2f}%)</span></div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            update_url()
            st.rerun()
    else:
        st.error(f"❌ 代碼 {code} 讀取失敗")

# 自動更新
time.sleep(60)
st.rerun()
