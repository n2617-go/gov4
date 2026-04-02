import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# ══════════════════════════════════════════════════════════
# 1. 技術指標運算與訊號判定
# ══════════════════════════════════════════════════════════
def compute_analysis(df, m_list):
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
        df['Upper'] = df['MA20'] + (df['STD'] * 2)
        df['Lower'] = df['MA20'] - (df['STD'] * 2)
        
        last, prev = df.iloc[-1], df.iloc[-2]
        
        # 判定各指標是否符合多方條件
        matches = []
        scores = []
        
        if "KD" in m_list:
            is_match = last['K'] < 30 and last['K'] > prev['K']
            if is_match: matches.append("🔥 KD低檔轉強")
            scores.append(90 if is_match else 50)
            
        if "MACD" in m_list:
            is_match = last['OSC'] > 0 and prev['OSC'] <= 0
            if is_match: matches.append("🚀 MACD翻紅")
            scores.append(95 if is_match else 50)
            
        if "RSI" in m_list:
            is_match = last['RSI'] < 40 and last['RSI'] > prev['RSI']
            if is_match: matches.append("📈 RSI轉強")
            scores.append(85 if is_match else 50)
            
        if "布林通道" in m_list:
            is_match = last['Close'] > last['MA20']
            if is_match: matches.append("🌌 站上月線")
            scores.append(90 if is_match else 50)
            
        if "成交量" in m_list:
            v_ma = df['Volume'].tail(5).mean()
            is_match = last['Volume'] > v_ma * 1.5
            if is_match: matches.append("📊 量能爆發")
            scores.append(90 if is_match else 50)

        score = int(sum(scores)/len(scores)) if scores else 50
        return df, score, matches
    except:
        return df, 50, []

# ══════════════════════════════════════════════════════════
# 2. 數據抓取與名稱修復
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_stock_full_info(code, m_list):
    for sfx in [".TW", ".TWO"]:
        try:
            tk = yf.Ticker(f"{code}{sfx}")
            df = tk.history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty and len(df) > 30:
                # 強制刷新 info 獲取中文名
                info = tk.info
                name = info.get('longName') or info.get('shortName') or code
                # 清洗名稱，若無中文則顯示代碼
                c_name = name if any(ord(c) > 127 for c in name) else f"股票 {code}"
                df_analyzed, score, matches = compute_analysis(df, m_list)
                return df_analyzed, c_name, score, matches
        except: continue
    return None, code, 50, []

# ══════════════════════════════════════════════════════════
# 3. UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 智能監控", layout="centered")

# CSS 美化：加入標籤樣式
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:15px; border-left:6px solid #38bdf8; margin-bottom:15px; }
    .tag { background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; margin-right: 5px; display: inline-block; margin-top: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
    .score-box { float:right; font-size:24px; font-weight:bold; border:2px solid; border-radius:50%; width:55px; height:55px; display:flex; align-items:center; justify-content:center; }
</style>
""", unsafe_allow_html=True)

# 儲存清單至 URL
DEFAULT_STOCKS = ["2330", "2317", "00631L", "2454", "2603"]
if "watchlist" not in st.session_state:
    params = st.query_params.get("wl", "")
    st.session_state.watchlist = params.split(",") if params else DEFAULT_STOCKS

def sync(): st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("🛡️ 台股 AI 全能監控系統")

# 側邊欄控制
with st.sidebar:
    st.header("⚙️ 決策因子配置")
    m_list = st.multiselect("勾選欲分析的指標：", 
                          ["KD", "MACD", "RSI", "布林通道", "成交量"], 
                          default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時漲跌預警門檻 (%)", 0.5, 5.0, 2.0)
    st.divider()
    if st.button("🔄 重置預設股票"):
        st.session_state.watchlist = DEFAULT_STOCKS
        sync(); st.rerun()

# 新增功能
with st.expander("➕ 新增關注標的", expanded=False):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入代碼", placeholder="例如: 8046").strip().upper()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                sync(); st.rerun()

# 渲染列表
for idx, code in enumerate(st.session_state.watchlist):
    df, c_name, score, matches = get_stock_full_info(code, m_list)
    
    if df is not None:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        color = "#ef4444" if score >= 70 else "#22c55e" if score <= 30 else "#94a3b8"
        
        # 建立符合指標的標籤 HTML
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        if not tags_html: tags_html = '<span style="color:#64748b; font-size:0.8rem;">目前無明顯指標訊號</span>'
        
        # 預警文字
        alert_msg = f"🚨 漲跌超過 {warn_p}% 預警！" if abs(chg) >= warn_p else ""

        st.markdown(f"""
        <div class="card" style="border-left-color: {color};">
            <div class="score-box" style="color: {color}; border-color: {color};">{score}</div>
            <div style="font-size: 1.2rem; font-weight: bold;">{c_name} ({code}) <span style="color:#f59e0b;">{alert_msg}</span></div>
            <div style="font-size: 1.8rem; font-weight: 900; color: {color}; margin: 5px 0;">
                {last['Close']:.2f} <span style="font-size: 1rem;">({chg:+.2f}%)</span>
            </div>
            <div style="margin-top: 5px;">
                <b>符合指標：</b><br>{tags_html}
            </div>
            <div style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.03); border-radius: 8px; font-size: 0.85rem; border: 1px solid rgba(255,255,255,0.1);">
                <b style="color:{color}">💡 AI 投資建議：</b><br>
                { "🔥 趨勢強勁，多頭指標共振，建議續抱。" if score >= 70 else "⚠️ 指標轉弱，建議適度減碼或觀望。" if score <= 30 else "⚖️ 目前盤整中，建議靜待指標突破。" }
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{idx}"):
            st.session_state.watchlist.remove(code)
            sync(); st.rerun()
    else:
        st.error(f"❌ {code} 資料讀取失敗")

time.sleep(60)
st.rerun()
