import streamlit as st
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
import urllib3

# 嘗試匯入 pandas_ta，若未安裝則顯示友善提示
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
    st.error("請在 requirements.txt 中加入 pandas-ta 以啟用 AI 技術分析功能。")

DEFAULT_LIST = [
    {"id": "2330", "name": "台積電"},
    {"id": "2317", "name": "鴻海"},
    {"id": "00631L", "name": "元大台灣50正2"},
    {"id": "2454", "name": "聯發科"},
    {"id": "00981A", "name": "統一台股增長"}
]

if "watchlist" not in st.session_state:
    try:
        url_params = st.query_params.get("wl", "")
        st.session_state.watchlist = json.loads(url_params) if url_params else DEFAULT_LIST
    except:
        st.session_state.watchlist = DEFAULT_LIST

# ══════════════════════════════════════════════════════════
# 2. 核心分析引擎 (5大指標邏輯)
# ══════════════════════════════════════════════════════════

def get_ai_analysis(df, active_metrics):
    if df is None or len(df) < 30 or not HAS_TA:
        return 50, "數據讀取中或套件缺失...", "#94a3b8", {}

    # 計算技術指標
    df.ta.kd(high='High', low='Low', close='Close', append=True) 
    df.ta.rsi(length=14, append=True) 
    df.ta.macd(append=True) 
    df.ta.bbands(length=20, std=2, append=True) 
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    ma20 = last['BBM_20_2.0']
    curr_p = last['Close']
    
    scores = []
    
    # 1. KD (權重)
    if "KD" in active_metrics:
        k, pk = last['K_9_3'], prev['K_9_3']
        if k < 25 and k > pk: scores.append(90)
        elif k > 75 and k < pk: scores.append(10)
        else: scores.append(50)

    # 2. MACD
    if "MACD" in active_metrics:
        hist, p_hist = last['MACDh_12_26_9'], prev['MACDh_12_26_9']
        if hist > 0 and p_hist <= 0: scores.append(95)
        elif hist < 0 and p_hist >= 0: scores.append(5)
        else: scores.append(50)

    # 3. RSI
    if "RSI" in active_metrics:
        rsi = last['RSI_14']
        if rsi < 30: scores.append(85)
        elif rsi > 70: scores.append(15)
        else: scores.append(50)

    # 4. 布林通道
    if "布林通道" in active_metrics:
        if curr_p > last['BBU_20_2.0']: scores.append(90)
        elif curr_p < last['BBL_20_2.0']: scores.append(10)
        else: scores.append(50)

    # 5. 成交量
    if "成交量" in active_metrics:
        avg_vol = df['Volume'].tail(5).mean()
        if last['Volume'] > avg_vol * 1.5 and curr_p > prev['Close']: scores.append(90)
        elif last['Volume'] > avg_vol * 1.5 and curr_p < prev['Close']: scores.append(10)
        else: scores.append(50)

    final_score = int(sum(scores) / len(scores)) if scores else 50
    
    # 動態建議邏輯
    color = "#94a3b8"
    advice = "⚖️ 指標震盪，建議靜待方向突破"
    
    if final_score >= 70:
        color = "#ef4444"
        if curr_p > ma20: advice = "🔥 趨勢偏多建議續抱，量價配合良好"
        else: advice = "🚀 殺低後站回，指標剛轉強，建議分批佈局"
    elif final_score <= 30:
        color = "#22c55e"
        if curr_p < ma20: advice = "📉 趨勢轉弱建議減碼，下方支撐不明"
        else: advice = "⚠️ 殺低後雖站回，但上方有壓，建議見好就收"

    return final_score, advice, color, {
        "price": curr_p, "k": last.get('K_9_3', 0), "d": last.get('D_9_3', 0),
        "rsi": last.get('RSI_14', 0), "macd": last.get('MACDh_12_26_9', 0)
    }

# ══════════════════════════════════════════════════════════
# 3. CSS 樣式
# ══════════════════════════════════════════════════════════
st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #0a0d14 !important; color: #e2e8f0 !important; font-family: 'Noto Sans TC', sans-serif !important; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.1); border-radius: 18px; padding: 1.2rem; margin-bottom: 1rem; border-left: 5px solid #38bdf8; }
.score-circle { width: 45px; height: 45px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1.1rem; border: 2px solid; }
.advice-box { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; margin-top: 10px; font-size: 0.85rem; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 4. 主介面
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🛠️ 決策指標設定")
    selected_metrics = st.multiselect(
        "選擇要啟用的分析指標：",
        ["KD", "MACD", "RSI", "布林通道", "成交量"],
        default=["KD", "MACD", "RSI", "布林通道", "成交量"]
    )
    st.divider()
    warn_p = st.slider("即時漲跌幅預警門檻 (%)", 0.5, 5.0, 2.0)
    if st.button("🔄 重置預設清單"):
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
    try:
        tk = yf.Ticker(f"{code}.TW")
        hist = tk.history(period="3mo")
        if hist.empty: continue
        
        score, advice, color, vals = get_ai_analysis(hist, selected_metrics)
        day_chg = ((vals['price'] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
        urgent_blink = "🚨" if abs(day_chg) >= warn_p else ""

        st.markdown(f"""
        <div class="stock-card" style="border-left-color: {color}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-weight:900; font-size:1.1rem;">{s['name']}</span>
                    <span style="color:#64748b; font-size:0.75rem; margin-left:5px;">{code}.TW {urgent_blink}</span>
                </div>
                <div class="score-circle" style="color: {color}; border-color: {color}">
                    {score}
                </div>
            </div>
            
            <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:10px;">
                <div style="font-size:1.5rem; font-weight:700;">{vals['price']:.2f} <span style="font-size:0.9rem; color:{color};">{day_chg:+.2f}%</span></div>
                <div style="text-align:right; font-size:0.7rem; color:#94a3b8;">
                    KD: {vals['k']:.1f}/{vals['d']:.1f} | RSI: {vals['rsi']:.1f}
                </div>
            </div>

            <div class="advice-box">
                <b style="color:{color}">💡 AI 進出場建議：</b><br>
                {advice}
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.pop(idx)
            st.query_params["wl"] = json.dumps(st.session_state.watchlist)
            st.rerun()
            
    except:
        st.error(f"代碼 {code} 讀取失敗")

time.sleep(60)
st.rerun()
