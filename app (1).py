import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import json

# ══════════════════════════════════════════════════════════
# 1. 技術指標數學公式 (自力救濟版，不需額外套件)
# ══════════════════════════════════════════════════════════

def compute_indicators(df):
    # RSI 計算
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # KD 計算 (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    df['K'] = rsv.ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()

    # MACD 計算 (12, 26, 9)
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
st.set_page_config(page_title="台股 AI 監控 (穩定版)", layout="centered")
st.markdown("<style>html, body, [data-testid='stAppViewContainer'] { background-color: #0a0d14 !important; color: white; }</style>", unsafe_allow_html=True)

if "watchlist" not in st.session_state:
    st.session_state.watchlist = [{"id": "2330", "name": "台積電"}]

with st.sidebar:
    st.header("⚙️ 決策設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 2.0)

st.title("📈 台股 AI 決策監控")

# 渲染卡片
for idx, s in enumerate(st.session_state.watchlist):
    df = get_stock_data(s['id'])
    if df is not None:
        score, advice, color, last = analyze_stock(df, m_list)
        chg = ((last['Close'] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100)
        
        st.markdown(f"""
        <div style="background:#111827; padding:20px; border-radius:15px; border-left:6px solid {color}; margin-bottom:10px;">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <h3 style="margin:0;">{s['name']} ({s['id']}) {"🚨" if abs(chg)>=warn_p else ""}</h3>
            <h2 style="color:{color}; margin:10px 0;">{last['Close']:.2f} <span style="font-size:16px;">({chg:+.2f}%)</span></h2>
            <div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:8px;">
                <b style="color:{color}">💡 AI 決策建議：</b><br>{advice}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error(f"代碼 {s['id']} 資料讀取失敗")

time.sleep(60)
st.rerun()
