import streamlit as st
import requests
import yfinance as yf
import time
import json
import pandas as pd
import urllib3

# 嘗試匯入技術分析套件，若失敗會顯示警告而非崩潰
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 智能監控", layout="centered")

if "watchlist" not in st.session_state:
    st.session_state.watchlist = [{"id": "2330", "name": "台積電"}, {"id": "2317", "name": "鴻海"}, {"id": "00631L", "name": "元大台灣50正2"}]

# ══════════════════════════════════════════════════════════
# 2. 數據與 AI 引擎
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def get_data(code):
    """支援上市(.TW)與上櫃(.TWO)抓取"""
    for sfx in [".TW", ".TWO"]:
        try:
            df = yf.Ticker(f"{code}{sfx}").history(period="6mo", interval="1d", auto_adjust=True)
            if not df.empty and len(df) > 20: return df
        except: continue
    return None

def run_ai_logic(df, metrics):
    if df is None or not HAS_TA: return 50, "分析中...", "#94a3b8", {}
    
    try:
        # 計算技術指標
        df.ta.kd(append=True); df.ta.rsi(append=True); df.ta.macd(append=True); df.ta.bbands(append=True)
        last, prev = df.iloc[-1], df.iloc[-2]
        
        scores = []
        # 1. KD
        if "KD" in metrics:
            k, pk = last.get('K_9_3', 50), prev.get('K_9_3', 50)
            scores.append(90 if k < 25 and k > pk else 10 if k > 75 and k < pk else 50)
        # 2. MACD
        if "MACD" in metrics:
            h, ph = last.get('MACDh_12_26_9', 0), prev.get('MACDh_12_26_9', 0)
            scores.append(95 if h > 0 and ph <= 0 else 50)
        # 3. RSI
        if "RSI" in metrics:
            r = last.get('RSI_14', 50)
            scores.append(85 if r < 30 else 15 if r > 70 else 50)
        # 4. 布林通道
        if "布林通道" in metrics:
            c, u, l = last['Close'], last.get('BBU_20_2.0', 9999), last.get('BBL_20_2.0', 0)
            scores.append(90 if c > u else 10 if c < l else 50)
        # 5. 成交量
        if "成交量" in metrics:
            v_ma = df['Volume'].tail(5).mean()
            scores.append(90 if last['Volume'] > v_ma * 1.5 and last['Close'] > prev['Close'] else 50)

        final_score = int(sum(scores) / len(scores)) if scores else 50
        
        # 進出場建議說明
        color = "#94a3b8"
        advice = "⚖️ 指標震盪，建議靜待方向突破"
        ma20 = last.get('BBM_20_2.0', last['Close'])
        
        if final_score >= 70:
            color = "#ef4444"
            advice = "🔥 趨勢偏多建議續抱" if last['Close'] > ma20 else "🚀 殺低後站回，趨勢偏多建議續抱"
        elif final_score <= 30:
            color = "#22c55e"
            advice = "📉 趨勢轉弱建議減碼" if last['Close'] < ma20 else "⚠️ 殺低後雖站回，上方有壓建議見好就收"

        return final_score, advice, color, {"p": last['Close'], "k": last.get('K_9_3',0), "r": last.get('RSI_14',0)}
    except:
        return 50, "計算異常", "#94a3b8", {"p": df['Close'].iloc[-1]}

# ══════════════════════════════════════════════════════════
# 3. 網頁介面
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background: #111827; border-left: 5px solid #38bdf8; padding: 1.5rem; border-radius: 12px; margin-bottom: 1rem; }
    .score { font-size: 24px; font-weight: bold; float: right; border: 2px solid; border-radius: 50%; width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 決策配置")
    m_list = st.multiselect("指標開關", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 2.0)
    if st.button("重置清單"):
        st.session_state.watchlist = [{"id": "2330", "name": "台積電"}]
        st.rerun()

st.title("📊 台股 AI 全能監控")

# 渲染列表
for idx, s in enumerate(st.session_state.watchlist):
    code = s['id']
    hist = get_data(code)
    
    if hist is not None:
        score, advice, color, val = run_ai_logic(hist, m_list)
        chg = ((val['p'] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100)
        
        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div class="score" style="color: {color}; border-color: {color}">{score}</div>
            <div style="font-size: 1.2rem; font-weight: bold;">{s['name']} ({code}) {"🚨" if abs(chg)>=warn_p else ""}</div>
            <div style="font-size: 1.8rem; font-weight: bold; color: {color};">{val['p']:.2f} <span style="font-size: 1rem;">({chg:+.2f}%)</span></div>
            <div style="margin-top: 10px; padding: 8px; background: rgba(255,255,255,0.05); border-radius: 5px;">
                <b style="color: {color}">💡 AI 決策建議：</b><br>{advice}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.pop(idx)
            st.rerun()
    else:
        st.error(f"無法讀取 {code} 資料")

# 每分鐘刷新
time.sleep(60)
st.rerun()
