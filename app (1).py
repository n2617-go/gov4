import streamlit as st
import pandas as pd
import yfinance as yf
import json
import time
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 系統初始化與 Cookies 永久儲存邏輯
# ══════════════════════════════════════════════════════════
controller = CookieController()
cookie_watchlist = controller.get('user_watchlist')

if "watchlist" not in st.session_state:
    if cookie_watchlist:
        try:
            st.session_state.watchlist = json.loads(cookie_watchlist)
        except:
            st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
    else:
        st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

# ══════════════════════════════════════════════════════════
# 2. 核心分析引擎：五大指標計算
# ══════════════════════════════════════════════════════════
def get_stock_data(code):
    yf_code = code + ".TW" if len(code) <= 4 else code + ".TWO"
    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period="6mo") # 抓半年數據確保指標精準
        if not df.empty:
            info = ticker.info
            name = info.get('longName') or info.get('shortName') or f"個股 {code}"
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return df.rename(columns={'high':'max', 'low':'min'}), name
    except: pass
    return pd.DataFrame(), f"代碼 {code}"

def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20:
        return 50, [], "數據不足", "累積數據中，請稍候...", "觀望", False

    # 數據清理
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    
    matches = []
    # --- 1. RSI (14日) ---
    diff = df['close'].diff()
    gain = diff.where(diff > 0, 0).rolling(14).mean()
    loss = -diff.where(diff < 0, 0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.0001))))
    
    # --- 2. KD (9日) ---
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()
    
    # --- 3. MACD ---
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    
    # --- 4. 布林通道 ---
    df['MA20'] = df['close'].rolling(20).mean()
    df['std'] = df['close'].rolling(20).std()
    df['Up'] = df['MA20'] + (df['std'] * 2)
    
    # --- 5. 成交量 ---
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    
    # 指標判定
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.5: matches.append("📊 量能爆發")

    # 漲跌幅門檻檢查
    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    
    # 決策說明
    status, strategy = "中性觀察", "觀望"
    reason = "目前各項技術指標訊號分散，建議靜待明確突破。"
    if len(matches) >= 3 and chg > 0:
        status, strategy = "多頭共振", "強力續抱"
        reason = f"符合 {len(matches)} 項指標，且股價處於上升軌道，動能極強。"
    elif last['close'] < last['MA20']:
        status, strategy = "轉弱訊號", "減碼規避"
        reason = "股價跌破 20 日月線支撐，短期趨勢轉空，需注意風險。"

    score = int(50 + (len(matches) * 10))
    return score, matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# 3. UI 渲染介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控旗艦版", layout="centered")

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; position: relative; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:10px 0; border:1px solid #1e293b; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; border:1px solid #334155; }
    .warn-label { background:#facc15; color:#000; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold; position:absolute; top:10px; right:20px; }
</style>
""", unsafe_allow_html=True)

# 側邊欄：功能開關與門檻
with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    
    st.divider()
    new_code = st.text_input("➕ 新增股票代碼")
    if st.button("確認新增"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
            st.success(f"已新增 {new_code}"); time.sleep(0.5); st.rerun()

st.title("⚡ AI 自動監控面板")

for code in list(st.session_state.watchlist):
    df, c_name = get_stock_data(code)
    if df.empty:
        st.warning(f"⚠️ 無法取得 {code} 數據"); continue

    # 分析並顯示
    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # 渲染卡片
    html_card = f'''
    <div class="card" style="border-left-color: {color}">
        {f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>' if is_warn else ''}
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.5rem; font-weight:bold;">{score}</div>
            <div style="color:#38bdf8; font-size:0.8rem; font-weight:bold;">{strategy}</div>
        </div>
        <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code})</div>
        <div style="font-size:2rem; font-weight:900; color:{color}; margin:10px 0;">
            {last_p:.2f} <small style="font-size:1rem;">({chg:+.2f}%)</small>
        </div>
        <div class="dec-box">
            <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold;">AI 決策：{status}</div>
            <div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">{reason}</div>
        </div>
        <div>{" ".join([f'<span class="tag">{m}</span>' for m in matches]) if matches else '<span style="color:#475569; font-size:0.7rem;">掃描訊號中...</span>'}</div>
    </div>
    '''
    st.markdown(html_card, unsafe_allow_html=True)
    
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code)
        controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
        st.rerun()
