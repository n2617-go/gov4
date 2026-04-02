
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import re

# ══════════════════════════════════════════════════════════
# 1. 中文名稱救援系統 (內建對照表 + 網頁爬蟲雙保險)
# ══════════════════════════════════════════════════════════
STOCK_DB = {
    "2330": "台積電", "2317": "鴻海", "00631L": "元大台灣50正2", 
    "2454": "聯發科", "2603": "長榮", "2308": "台達電", 
    "2382": "廣達", "2357": "華碩", "3008": "大立光", "0050": "元大台灣50"
}

def get_chinese_name(code):
    if code in STOCK_DB:
        return STOCK_DB[code]
    try:
        # 爬取 Yahoo Finance 網頁標題來獲取精準中文名
        url = f"https://tw.stock.yahoo.com/quote/{code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        pattern = r"<title>(.*?) \({code}\)".format(code=code)
        match = re.search(pattern, response.text)
        if match:
            return match.group(1)
    except:
        pass
    return f"個股 {code}"

# ══════════════════════════════════════════════════════════
# 2. 極短線技術指標與訊號
# ══════════════════════════════════════════════════════════
def analyze_momentum(df, m_list):
    df = df.copy()
    # RSI (快速版)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    # KD (短線參數 9,3)
    low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # MACD (標準)
    exp1, exp2 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp1 - exp2
    df['DEM'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['OSC'] = df['DIF'] - df['DEM']
    
    # 布林通道
    df['MA20'] = df['Close'].rolling(20).mean()
    df['STD'] = df['Close'].rolling(20).std()
    df['Upper'], df['Lower'] = df['MA20'] + (df['STD'] * 2), df['MA20'] - (df['STD'] * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    
    # 判斷邏輯
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("MACD翻紅訊號")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("突破布林上軌")
    if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("量能異常爆發")
    
    score = 50 + (len(matches) * 10) if last['Close'] > prev['Close'] else 50 - (len(matches) * 10)
    return score, matches, last

# ══════════════════════════════════════════════════════════
# 3. Streamlit 主介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:12px; }
    .signal-tag { background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; margin-right: 5px; border: 1px solid #38bdf8; }
</style>
""", unsafe_allow_html=True)

# 儲存機制
DEFAULT_STOCKS = ["2330", "2317", "00631L", "2454", "2603"]
if "watchlist" not in st.session_state:
    params = st.query_params.get("wl", "")
    st.session_state.watchlist = params.split(",") if params else DEFAULT_STOCKS

def sync(): st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("⚡ 台股極短線 AI 監控系統")

# 側邊欄控制
with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用決策指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時預警門檻 (%)", 0.5, 5.0, 1.5)
    if st.button("🔄 恢復預設"):
        st.session_state.watchlist = DEFAULT_STOCKS
        sync(); st.rerun()

# 新增股票
with st.expander("➕ 新增監控股票"):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入代碼").strip().upper()
    with c2:
        if st.button("確認加入"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                sync(); st.rerun()

st.divider()

# 核心循環
for code in st.session_state.watchlist:
    # 嘗試抓取數據
    data_found = False
    for sfx in [".TW", ".TWO"]:
        tk = yf.Ticker(f"{code}{sfx}")
        df = tk.history(period="1mo", interval="1d") # 極短線用較短歷史提高速度
        if not df.empty:
            data_found = True
            c_name = get_chinese_name(code)
            score, matches, last = analyze_momentum(df, m_list)
            
            # 計算漲跌幅
            prev_close = df.iloc[-2]['Close']
            chg_pct = (last['Close'] - prev_close) / prev_close * 100
            color = "#ef4444" if chg_pct > 0 else "#22c55e"
            score_color = "#38bdf8" if score >= 60 else "#94a3b8"

            # 符合指標 HTML
            tags = "".join([f'<span class="signal-tag">{m}</span>' for m in matches])
            alert = f"<span style='color:#facc15;'>🚨 震盪預警({warn_p}%)</span>" if abs(chg_pct) >= warn_p else ""

            st.markdown(f"""
            <div class="card" style="border-left-color: {score_color}">
                <div style="float:right; font-size:22px; font-weight:bold; color:{score_color};">{score}分</div>
                <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) {alert}</div>
                <div style="font-size:1.6rem; font-weight:900; color:{color}; margin:8px 0;">
                    {last['Close']:.2f} <span style="font-size:0.9rem;">({chg_pct:+.2f}%)</span>
                </div>
                <div style="margin-bottom:10px;">{tags if tags else '<span style="color:#475569; font-size:0.8rem;">監控中...</span>'}</div>
                <div style="font-size:0.85rem; color:#94a3b8; background:rgba(255,255,255,0.03); padding:8px; border-radius:5px;">
                    <b>AI 短線建議：</b> { "🔥 強勢噴發，建議續抱" if score >= 70 else "📉 走勢轉弱，建議減碼" if score <= 30 else "⚖️ 區間震盪，不宜追高" }
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
                st.session_state.watchlist.remove(code)
                sync(); st.rerun()
            break
    
    if not data_found:
        st.error(f"無法載入代碼 {code}")

# 即時掃描刷新 (極短線建議 30 秒一次)
time.sleep(30)
st.rerun()
