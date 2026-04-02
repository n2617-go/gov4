import streamlit as st
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
import pandas_ta as ta
import urllib3

# 忽略 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 智能全能監控", layout="centered", initial_sidebar_state="expanded")

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
# 2. 核心分析引擎 (5大指標)
# ══════════════════════════════════════════════════════════

def get_ai_analysis(df, active_metrics):
    """計算 AI 分數與生成口語建議"""
    if df is None or len(df) < 30:
        return 50, "數據讀取中...", "#94a3b8", {}

    # 計算技術指標
    df.ta.kd(high='High', low='Low', close='Close', append=True) # K_9_3, D_9_3
    df.ta.rsi(length=14, append=True) # RSI_14
    df.ta.macd(append=True) # MACDh_12_26_9
    df.ta.bbands(length=20, std=2, append=True) # BBU_20_2.0, BBM_20_2.0, BBL_20_2.0
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    ma20 = last['BBM_20_2.0']
    curr_p = last['Close']
    
    scores = []
    reasons = []

    # 1. KD 分析
    if "KD" in active_metrics:
        k, d = last['K_9_3'], last['D_9_3']
        pk = prev['K_9_3']
        if k < 25 and k > pk: 
            scores.append(90); reasons.append("KD低檔金叉")
        elif k > 75 and k < pk: 
            scores.append(10); reasons.append("KD高檔死叉")
        else: scores.append(50)

    # 2. MACD 分析
    if "MACD" in active_metrics:
        hist = last['MACDh_12_26_9']
        p_hist = prev['MACDh_12_26_9']
        if hist > 0 and p_hist <= 0:
            scores.append(90); reasons.append("MACD轉正")
        elif hist < 0 and p_hist >= 0:
            scores.append(10); reasons.append("MACD轉負")
        else: scores.append(50)

    # 3. RSI 分析
    if "RSI" in active_metrics:
        rsi = last['RSI_14']
        if rsi < 30: scores.append(85); reasons.append("RSI超跌反彈")
        elif rsi > 70: scores.append(15); reasons.append("RSI超漲過熱")
        else: scores.append(50)

    # 4. 布林通道 (BB)
    if "布林通道" in active_metrics:
        if curr_p > last['BBU_20_2.0']:
            scores.append(95); reasons.append("突破布林上軌")
        elif curr_p < last['BBL_20_2.0']:
            scores.append(5); reasons.append("跌破布林下軌")
        elif curr_p > ma20 and prev['Close'] <= ma20:
            scores.append(80); reasons.append("站回月線支撐")
        else: scores.append(50)

    # 5. 成交量 (Volume)
    if "成交量" in active_metrics:
        avg_vol = df['Volume'].tail(5).mean()
        if last['Volume'] > avg_vol * 1.5 and curr_p > prev['Close']:
            scores.append(90); reasons.append("量增價揚")
        elif last['Volume'] > avg_vol * 1.5 and curr_p < prev['Close']:
            scores.append(10); reasons.append("爆量下跌")
        else: scores.append(50)

    # 計算總分
    final_score = int(sum(scores) / len(scores)) if scores else 50
    
    # 產出口語化進出場建議
    color = "#94a3b8" # 預設灰色
    advice = "⚖️ 指標震盪，建議靜待方向突破"
    
    if final_score >= 75:
        color = "#ef4444" # 紅色
        if curr_p > ma20: advice = "🔥 趨勢偏多建議續抱，量價配合良好"
        else: advice = "🚀 殺低後站回，指標剛轉強，建議小量試單"
    elif final_score <= 35:
        color = "#22c55e" # 綠色
        if curr_p < ma20: advice = "📉 趨勢轉弱建議減碼，下方支撐不明"
        else: advice = "⚠️ 殺低後雖站回，但上方有壓，建議見好就收"

    return final_score, advice, color, {
        "price": curr_p,
        "k": last['K_9_3'], "d": last['D_9_3'],
        "rsi": last['RSI_14'], "macd": last['MACDh_12_26_9']
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
.price-text { font-size: 1.6rem; font-weight: 700; font-family: 'Monaco', monospace; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 4. 主介面交互
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🛠️ 決策指標設定")
    selected_metrics = st.multiselect(
        "選擇要啟用的分析指標：",
        ["KD", "MACD", "RSI", "布林通道", "成交量"],
        default=["KD", "MACD", "RSI"]
    )
    st.divider()
    warn_p = st.slider("即時漲跌幅預警門檻 (%)", 0.5, 5.0, 2.0)
    
    if st.button("🔄 重置預設清單"):
        st.query_params.clear()
        st.session_state.watchlist = DEFAULT_LIST
        st.rerun()

st.title("📊 台股 AI 智能決策系統")

# 新增股票邏輯
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
        
        # 即時漲跌計算
        day_chg = ((vals['price'] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
        urgent_blink = "🚨" if abs(day_chg) >= warn_p else ""

        st.markdown(f"""
        <div class="stock-card" style="border-left-color: {color}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-weight:900; font-size:1.2rem;">{s['name']}</span>
                    <span style="color:#64748b; font-size:0.8rem; margin-left:5px;">{code}.TW {urgent_blink}</span>
                </div>
                <div class="score-circle" style="color: {color}; border-color: {color}">
                    {score}
                </div>
            </div>
            
            <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:10px;">
                <div class="price-text">{vals['price']:.2f} <span style="font-size:1rem; color:{color};">{day_chg:+.2f}%</span></div>
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
            
    except Exception as e:
        st.error(f"代碼 {code} 讀取失敗")

# 自動刷新
time.sleep(60)
st.rerun()
