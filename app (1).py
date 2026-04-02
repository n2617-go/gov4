import streamlit as st
import requests
import yfinance as yf
import time
import json
import pandas as pd
import urllib3

# 嘗試匯入技術分析套件
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 監控 (穩定版)", layout="centered")

# 初始化自選股
if "watchlist" not in st.session_state:
    st.session_state.watchlist = [{"id": "2330", "name": "台積電"}, {"id": "2317", "name": "鴻海"}]

# ══════════════════════════════════════════════════════════
# 2. 數據抓取引擎 (FinMind API + yfinance 備援)
# ══════════════════════════════════════════════════════════

def get_stock_data(code, token=""):
    """優先嘗試 FinMind API，失敗則轉 yfinance"""
    # 如果有 Token，可以用 requests 呼叫，不需安裝 FinMind 套件
    if token:
        try:
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={code}&token={token}"
            # 這裡僅為範例，實務上 FinMind 歷史資料抓取較複雜，建議短線分析仍用 yfinance 較快
            pass 
        except: pass

    # yfinance 抓取 (最穩定且免費)
    for sfx in [".TW", ".TWO"]:
        try:
            df = yf.Ticker(f"{code}{sfx}").history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty: return df
        except: continue
    return None

def calculate_ai(df, metrics):
    if df is None or not HAS_TA: return 50, "讀取中", "#94a3b8", {}
    
    try:
        df.ta.kd(append=True); df.ta.rsi(append=True); df.ta.macd(append=True); df.ta.bbands(append=True)
        last, prev = df.iloc[-1], df.iloc[-2]
        
        score = 50
        # 簡單決策邏輯
        if "KD" in metrics and last.get('K_9_3', 50) < 25: score += 20
        if "布林通道" in metrics and last['Close'] > last.get('BBU_20_2.0', 9999): score += 20
        
        color = "#ef4444" if score > 60 else "#22c55e" if score < 40 else "#94a3b8"
        advice = "🚀 趨勢偏多建議續抱" if score > 60 else "⚠️ 上方有壓建議見好就收" if score < 40 else "⚖️ 觀望中"
        
        return score, advice, color, {"price": last['Close'], "k": last.get('K_9_3',0)}
    except:
        return 50, "計算異常", "#94a3b8", {"price": df['Close'].iloc[-1]}

# ══════════════════════════════════════════════════════════
# 3. 介面
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ 設定")
    fm_token = st.text_input("FinMind Token (選填)", type="password")
    active_m = st.multiselect("分析指標", ["KD", "MACD", "RSI", "布林通道"], default=["KD", "布林通道"])
    warn_p = st.slider("漲跌預警 (%)", 0.5, 5.0, 2.0)

st.title("📈 AI 智能監控系統")

for idx, s in enumerate(st.session_state.watchlist):
    code = s['id']
    hist = get_stock_data(code)
    
    if hist is not None:
        score, advice, color, vals = calculate_ai(hist, active_m)
        day_chg = ((vals['price'] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
        
        st.markdown(f"""
        <div style="border-left: 5px solid {color}; padding:15px; background:#111827; border-radius:10px; margin-bottom:10px;">
            <h3 style="margin:0;">{s['name']} ({code}) {"🚨" if abs(day_chg)>=warn_p else ""}</h3>
            <p style="font-size:20px; font-weight:bold; color:{color};">{vals['price']:.2f} ({day_chg:+.2f}%)</p>
            <p style="font-size:14px;"><b>AI 建議：</b>{advice}</p>
        </div>
        """, unsafe_allow_html=True)

# 每一分鐘自動刷新
time.sleep(60)
st.rerun()
