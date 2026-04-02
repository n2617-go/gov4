import streamlit as st
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
import urllib3

# 強制嘗試匯入 pandas_ta
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 智能全能監控", layout="centered", initial_sidebar_state="expanded")

if not HAS_TA:
    st.warning("⚠️ 系統正在安裝技術分析套件 (pandas-ta)，若剛更新 requirements.txt，請點擊右下角 Reboot 重啟。")

# 預設清單
DEFAULT_LIST = [
    {"id": "2330", "name": "台積電"},
    {"id": "2317", "name": "鴻海"},
    {"id": "00631L", "name": "元大台灣50正2"}
]

if "watchlist" not in st.session_state:
    try:
        url_params = st.query_params.get("wl", "")
        st.session_state.watchlist = json.loads(url_params) if url_params else DEFAULT_LIST
    except:
        st.session_state.watchlist = DEFAULT_LIST

# ══════════════════════════════════════════════════════════
# 2. 核心分析引擎 (修正數據抓取穩定性)
# ══════════════════════════════════════════════════════════

def get_stock_data(code):
    """強化版數據抓取：增加重試機制"""
    symbols = [f"{code}.TW", f"{code}.TWO"] # 同時考慮上市與上櫃
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            # 增加 auto_adjust 提高相容性
            df = ticker.history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty and len(df) > 30:
                return df
        except:
            continue
    return None

def get_ai_analysis(df, active_metrics):
    if df is None or not HAS_TA:
        return 50, "計算中...", "#94a3b8", {}

    # 清除 NaN 避免計算錯誤
    df = df.copy()
    
    # 計算指標 (使用 pandas_ta)
    try:
        df.ta.kd(high='High', low='Low', close='Close', append=True) 
        df.ta.rsi(length=14, append=True) 
        df.ta.macd(append=True) 
        df.ta.bbands(length=20, std=2, append=True) 
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        # 抓取正確的欄位名稱 (pandas_ta 命名有時會變動)
        k = last.get('K_9_3', 50)
        pk = prev.get('K_9_3', 50)
        rsi = last.get('RSI_14', 50)
        hist = last.get('MACDh_12_26_9', 0)
        ma20 = last.get('BBM_20_2.0', last['Close'])
        upper = last.get('BBU_20_2.0', last['Close'])
        lower = last.get('BBL_20_2.0', last['Close'])
        
        scores = []
        # --- 決策權重邏輯 ---
        if "KD" in active_metrics:
            scores.append(90 if k < 25 and k > pk else 10 if k > 75 and k < pk else 50)
        if "MACD" in active_metrics:
            scores.append(95 if hist > 0 and prev.get('MACDh_12_26_9', 0) <= 0 else 50)
        if "RSI" in active_metrics:
            scores.append(85 if rsi < 30 else 15 if rsi > 70 else 50)
        if "布林通道" in active_metrics:
            scores.append(90 if last['Close'] > upper else 10 if last['Close'] < lower else 50)
        if "成交量" in active_metrics:
            v_ma = df['Volume'].tail(5).mean()
            scores.append(90 if last['Volume'] > v_ma * 1.5 and last['Close'] > prev['Close'] else 50)

        final_score = int(sum(scores) / len(scores)) if scores else 50
        
        # 建議說明
        color = "#94a3b8"
        advice = "⚖️ 指標震盪，建議靜待方向突破"
        if final_score >= 70:
            color = "#ef4444"
            advice = "🔥 趨勢偏多建議續抱" if last['Close'] > ma20 else "🚀 殺低後站回，低檔剛轉強，建議小量試單"
        elif final_score <= 30:
            color = "#22c55e"
            advice = "📉 趨勢轉弱建議減碼" if last['Close'] < ma20 else "⚠️ 殺低後雖站回，但上方有壓，建議見好就收"

        return final_score, advice, color, {"price": last['Close'], "k": k, "rsi": rsi}
    except:
        return 50, "指標分析錯誤", "#94a3b8", {"price": df['Close'].iloc[-1]}

# ══════════════════════════════════════════════════════════
# 3. UI 介面
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #0a0d14 !important; color: #e2e8f0 !important; font-family: 'Noto Sans TC', sans-serif !important; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.1); border-radius: 18px; padding: 1.2rem; margin-bottom: 1rem; border-left: 5px solid #38bdf8; }
.score-circle { width: 45px; height: 45px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; border: 2px solid; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ 決策指標")
    selected_metrics = st.multiselect(
        "啟用指標：", ["KD", "MACD", "RSI", "布林通道", "成交量"],
        default=["KD", "MACD", "RSI", "布林通道", "成交量"]
    )
    warn_p = st.slider("漲跌預警 (%)", 0.5, 5.0, 2.0)
    if st.button("🔄 重置清單"):
        st.query_params.clear()
        st.session_state.watchlist = DEFAULT_LIST
        st.rerun()

st.title("📊 台股 AI 全能監控系統")

# 新增股票
with st.expander("➕ 新增關注股票"):
    col1, col2 = st.columns([3,1])
    with col1: nid = st.text_input("輸入代碼 (例: 00981A)").strip().upper()
    with col2:
        if st.button("加入"):
            if nid and not any(x['id'] == nid for x in st.session_state.watchlist):
                st.session_state.watchlist.append({"id": nid, "name": nid})
                st.query_params["wl"] = json.dumps(st.session_state.watchlist)
                st.rerun()

# 顯示監控
for idx, s in enumerate(st.session_state.watchlist):
    code = s['id']
    hist = get_stock_data(code)
    
    if hist is None:
        st.error(f"❌ 代碼 {code} 讀取失敗，請確認代碼是否正確或重試。")
        continue
    
    score, advice, color, vals = get_ai_analysis(hist, selected_metrics)
    day_chg = ((vals['price'] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
    blink = "🚨" if abs(day_chg) >= warn_p else ""

    st.markdown(f"""
    <div class="stock-card" style="border-left-color: {color}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-weight:900; font-size:1.1rem;">{s['name']}</span>
                <span style="color:#64748b; font-size:0.75rem; margin-left:5px;">{code}.TW {blink}</span>
            </div>
            <div class="score-circle" style="color: {color}; border-color: {color}">{score}</div>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:10px;">
            <div style="font-size:1.5rem; font-weight:700;">{vals['price']:.2f} <span style="font-size:0.9rem; color:{color};">{day_chg:+.2f}%</span></div>
            <div style="text-align:right; font-size:0.7rem; color:#94a3b8;">
                KD: {vals.get('k', 0):.1f} | RSI: {vals.get('rsi', 0):.1f}
            </div>
        </div>
        <div style="background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; margin-top: 10px; font-size: 0.85rem;">
            <b style="color:{color}">💡 AI 進出場建議：</b><br>{advice}
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.pop(idx)
        st.query_params["wl"] = json.dumps(st.session_state.watchlist)
        st.rerun()

time.sleep(60)
st.rerun()
