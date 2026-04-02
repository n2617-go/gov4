import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController # 新增：Cookies 控制器

# ══════════════════════════════════════════════════════════
# 1. 初始化與 Cookies 處理
# ══════════════════════════════════════════════════════════
controller = CookieController()

# 從 Cookies 嘗試讀取 Token
cookie_token = controller.get('finmind_token')

if "watchlist" not in st.session_state: 
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

# 如果 Session 沒 Token 但 Cookie 有，則自動補回
if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 核心功能函式 (保持不變)
# ══════════════════════════════════════════════════════════
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=13, minute=35)

def get_smart_data(code, token):
    if not is_trading_time() or not token:
        yf_code = code + ".TW" if len(code) == 4 else code + ".TWO"
        try:
            df = yf.Ticker(yf_code).history(period="1mo")
            if not df.empty:
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                return df.rename(columns={'high': 'max', 'low': 'min', 'volume': 'volume'}), "Yahoo"
        except: pass

    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
    headers = {"Authorization": "Bearer " + token}
    params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        df = pd.DataFrame(res.json().get("data", []))
        if not df.empty:
            return df.rename(columns={'Trading_Volume': 'volume'}), "FinMind"
    except: pass
    return pd.DataFrame(), "Error"

def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20: return 50, [], "分析中", "數據載入中", "觀望", False
    df['close'] = pd.to_numeric(df['close'])
    df['max'] = pd.to_numeric(df['max'])
    df['min'] = pd.to_numeric(df['min'])
    df['volume'] = pd.to_numeric(df['volume'])
    
    # 指標計算 (簡化示意，邏輯同前)
    diff = df['close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff > 0, 0).rolling(14).mean() / (-diff.where(diff < 0, 0).rolling(14).mean() + 0.0001))))
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()
    ema12, ema26 = df['close'].ewm(span=12).mean(), df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['close'].rolling(20).std() * 2)
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.5: matches.append("📊 量能爆發")

    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    status, reason, strategy = "觀察中", "尚無明顯趨勢。", "觀望"
    if len(matches) >= 3 and chg > 0: status, reason, strategy = "多頭趨勢", "多指標共振轉強。", "強力續抱"
    elif last['close'] < last['MA20']: status, reason, strategy = "支撐跌破", "跌破月線請注意風險。", "減碼"

    return int(50 + len(matches)*10), matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# 3. 登入介面與 Cookies 寫入
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控 (記住登入)", layout="centered")

if not st.session_state.get("tk"):
    st.title("🛡️ 權限驗證")
    tk_input = st.text_input("輸入 Token", type="password")
    remember = st.checkbox("記住我的 Token (30 天內免輸入)")
    
    if st.button("登入系統"):
        if tk_input:
            st.session_state.tk = tk_input
            if remember:
                # 寫入 Cookies，有效期 30 天
                controller.set('finmind_token', tk_input, max_age=2592000)
            st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════
# 4. 主面板 (與之前版本相同，僅修改登出)
# ══════════════════════════════════════════════════════════
st.title("⚡ AI 自動監控面板")

with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    
    if st.button("🚪 登出系統"):
        # 清除 Cookies 與 Session
        controller.remove('finmind_token')
        st.session_state.tk = ""
        st.rerun()

# 渲染邏輯 (與之前版本一致...)
for code in list(st.session_state.watchlist):
    df, source = get_smart_data(code, st.session_state.tk)
    if df.empty: continue
    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    html_card = '<div style="background:#111827; padding:18px; border-radius:12px; border-left:6px solid '+color+'; margin-bottom:15px; border:1px solid #1e2533; position: relative;">'
    if is_warn: html_card += '<div style="background:#facc15; color:#000; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold; position:absolute; top:10px; right:80px;">⚠️ 波動預警</div>'
    html_card += '<div style="float:right; color:'+color+'; font-size:1.3rem; font-weight:bold;">' + str(score) + '</div>'
    html_card += '<div style="font-size:1rem; font-weight:bold;">個股監控 (' + code + ')</div>'
    html_card += '<div style="font-size:1.8rem; font-weight:900; color:' + color + ';">' + f"{last_p:.2f}" + ' <span style="font-size:1rem;">(' + f"{chg:+.2f}" + '%)</span></div>'
    html_card += '<div style="background:#0f172a; padding:10px; border-radius:8px; margin:10px 0;">AI 決策：' + status + '<br><small>' + reason + '</small></div>'
    html_card += '</div>'
    
    st.markdown(html_card, unsafe_allow_html=True)
