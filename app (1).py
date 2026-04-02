import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# ══════════════════════════════════════════════════════════
# 1. 核心技術指標運算 (自寫版，確保不當機)
# ══════════════════════════════════════════════════════════
def compute_indicators(df):
    try:
        df = df.copy()
        # RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        # KD (9, 3, 3)
        low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()
        # MACD (12, 26, 9)
        exp1, exp2 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = exp1 - exp2
        df['DEM'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['DEM']
        # 布林通道 (20, 2)
        df['MA20'] = df['Close'].rolling(20).mean()
        df['STD'] = df['Close'].rolling(20).std()
        df['Upper'], df['Lower'] = df['MA20'] + (df['STD'] * 2), df['MA20'] - (df['STD'] * 2)
        return df
    except: return df

# ══════════════════════════════════════════════════════════
# 2. 數據抓取與中文名稱處理
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def fetch_stock(code):
    for sfx in [".TW", ".TWO"]:
        try:
            tk = yf.Ticker(f"{code}{sfx}")
            df = tk.history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty and len(df) > 30:
                # 獲取中文名稱 (Yahoo 有時回傳英文，若無中文則顯示代碼)
                raw_name = tk.info.get('longName', code)
                # 判斷是否含中文或特定字元
                disp_name = raw_name if any(ord(c) > 127 for c in raw_name) else f"股票 {code}"
                return compute_indicators(df), disp_name
        except: continue
    return None, None

# ══════════════════════════════════════════════════════════
# 3. UI 介面與功能整合
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 決策監控", layout="centered")

# CSS 美化
st.markdown("<style>html, body, [data-testid='stAppViewContainer'] { background-color: #0a0d14 !important; color: white; }</style>", unsafe_allow_html=True)

# 初始化 Session 與 URL 同步
DEFAULT_STOCKS = ["2330", "2317", "00631L", "2454", "2603"]
if "watchlist" not in st.session_state:
    params = st.query_params.get("wl", "")
    st.session_state.watchlist = params.split(",") if params else DEFAULT_STOCKS

def sync(): st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("📊 台股 AI 決策全能監控")

# --- 側邊欄：決策指標勾選與預警 ---
with st.sidebar:
    st.header("⚙️ 監控配置")
    m_list = st.multiselect("啟用分析指標 (勾選後影響評分)", 
                          ["KD", "MACD", "RSI", "布林通道", "成交量"], 
                          default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時漲跌預警門檻 (%)", 0.5, 5.0, 2.0)
    st.divider()
    if st.button("🔄 恢復預設五檔"):
        st.session_state.watchlist = DEFAULT_STOCKS
        sync(); st.rerun()

# --- 新增功能 ---
with st.expander("➕ 新增關注股票", expanded=True):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入代碼", placeholder="例如: 2330").strip().upper()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                sync(); st.rerun()

st.divider()

# --- 股票渲染邏輯 ---
for idx, code in enumerate(st.session_state.watchlist):
    df, c_name = fetch_stock(code)
    if df is not None:
        last, prev = df.iloc[-1], df.iloc[-2]
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        
        # 4. AI 評分邏輯 (根據使用者勾選的指標計算)
        scores = []
        if "KD" in m_list: scores.append(90 if last['K'] < 25 and last['K'] > prev['K'] else 10 if last['K'] > 75 and last['K'] < prev['K'] else 50)
        if "MACD" in m_list: scores.append(95 if last['OSC'] > 0 and prev['OSC'] <= 0 else 50)
        if "RSI" in m_list: scores.append(85 if last['RSI'] < 30 else 15 if last['RSI'] > 70 else 50)
        if "布林通道" in m_list: scores.append(90 if last['Close'] > last['Upper'] else 10 if last['Close'] < last['Lower'] else 50)
        if "成交量" in m_list:
            v_ma = df['Volume'].tail(5).mean()
            scores.append(90 if last['Volume'] > v_ma * 1.5 and last['Close'] > prev['Close'] else 50)
        
        score = int(sum(scores)/len(scores)) if scores else 50
        color = "#ef4444" if score >= 70 else "#22c55e" if score <= 30 else "#94a3b8"
        
        # 進出場建議說明
        advice = "⚖️ 指標震盪，建議靜待方向突破"
        if score >= 70:
            advice = "🔥 趨勢偏多建議續抱" if last['Close'] > last['MA20'] else "🚀 低檔轉強，建議分批佈局"
        elif score <= 30:
            advice = "📉 趨勢轉弱建議減碼" if last['Close'] < last['MA20'] else "⚠️ 上方有壓，建議見好就收"

        st.markdown(f"""
        <div style="background:#111827; padding:20px; border-radius:15px; border-left:6px solid {color}; margin-bottom:10px;">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size: 1.1rem; font-weight: bold;">{c_name} ({code}) {"🚨" if abs(chg)>=warn_p else ""}</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: {color};">{last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
            <div style="margin-top:10px; padding:10px; background:rgba(255,255,255,0.05); border-radius:8px;">
                <b style="color:{color}">💡 AI 決策建議：</b><br>{advice}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            sync(); st.rerun()
    else:
        st.error(f"❌ 代碼 {code} 讀取失敗，請確認代碼或稍後再試。")

time.sleep(60)
st.rerun()
