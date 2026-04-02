import streamlit as st
import pandas as pd
import yfinance as yf
import json
import time
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 系統初始化與 Cookies 讀取
# ══════════════════════════════════════════════════════════
controller = CookieController()

# 取得 Cookie
cookie_watchlist = controller.get('user_watchlist')
cookie_token = controller.get('finmind_token')

# 初始化 Watchlist (確保這段邏輯在最前面)
if "watchlist" not in st.session_state:
    if cookie_watchlist:
        try:
            st.session_state.watchlist = json.loads(cookie_watchlist)
        except:
            st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
    else:
        st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 核心函式
# ══════════════════════════════════════════════════════════
def get_stock_data(code):
    """抓取數據並回傳 (df, name)"""
    yf_code = code + ".TW" if len(code) <= 4 else code + ".TWO"
    try:
        ticker = yf.Ticker(yf_code)
        # 增加至 6 個月確保指標計算穩定
        df = ticker.history(period="6mo")
        if not df.empty:
            info = ticker.info
            name = info.get('longName') or info.get('shortName') or f"個股 {code}"
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return df.rename(columns={'high':'max', 'low':'min'}), name
    except Exception as e:
        print(f"Error fetching {code}: {e}")
    return pd.DataFrame(), f"代碼 {code}"

def analyze_stock(df, m_list):
    """計算指標與決策"""
    if df.empty or len(df) < 20:
        return 50, [], "數據不足", "正在累積歷史數據...", "觀望"
    
    # 指標計算
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    
    matches = []
    # RSI
    diff = df['close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff > 0, 0).rolling(14).mean() / (-diff.where(diff < 0, 0).rolling(14).mean() + 0.0001))))
    # MA20
    df['MA20'] = df['close'].rolling(20).mean()
    
    last, prev = df.iloc[-1], df.iloc[-2]
    
    if last['RSI'] > 55: matches.append("📈 RSI走強")
    if last['close'] > last['MA20']: matches.append("🚀 站上月線")
    
    status = "多頭趨勢" if len(matches) >= 1 else "空頭整理"
    reason = "股價位於月線上方且動能轉強。" if status == "多頭趨勢" else "目前量價結構尚需觀察。"
    strategy = "續抱/加碼" if status == "多頭趨勢" else "觀望"
    
    return 70 if status == "多頭趨勢" else 40, matches, status, reason, strategy

# ══════════════════════════════════════════════════════════
# 3. UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控", layout="centered")

# 樣式定義
st.markdown("""
<style>
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:10px 0; border:1px solid #1e293b; color:#f1f5f9; font-size:0.85rem; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; border:1px solid #334155; }
</style>
""", unsafe_allow_html=True)

# 側邊欄
with st.sidebar:
    st.header("⚙️ 控制中心")
    new_code = st.text_input("➕ 新增股票代碼")
    if st.button("確認新增"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
            st.success(f"已新增 {new_code}")
            time.sleep(0.5)
            st.rerun()
    
    if st.button("🧹 重設所有清單"):
        st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
        controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
        st.rerun()

st.title("⚡ AI 自動監控面板")

# 顯示股票卡片
# 使用 list() 確保迴圈穩定
for code in list(st.session_state.watchlist):
    df, c_name = get_stock_data(code)
    
    # 即使數據為空也顯示一個「錯誤卡片」，這樣您才知道程式有在跑
    if df.empty:
        st.warning(f"⚠️ 無法取得 {code} 的數據，可能是代碼錯誤或 Yahoo 暫時阻擋。")
        if st.button(f"🗑️ 移除錯誤代碼 {code}", key=f"err_{code}"):
            st.session_state.watchlist.remove(code)
            controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
            st.rerun()
        continue

    # 分析數據
    score, matches, status, reason, strategy = analyze_stock(df, [])
    
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # 渲染 HTML 卡片
    html_card = f'''
    <div class="card" style="border-left-color: {color}">
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.5rem; font-weight:bold;">{score}</div>
            <div style="color:#38bdf8; font-size:0.8rem;">{strategy}</div>
        </div>
        <div style="font-size:1.2rem; font-weight:bold;">{c_name} ({code})</div>
        <div style="font-size:2rem; font-weight:900; color:{color}; margin:10px 0;">
            {last_p:.2f} <small style="font-size:1.1rem;">({chg:+.2f}%)</small>
        </div>
        <div class="dec-box">
            <b>AI 決策：{status}</b><br>{reason}
        </div>
        <div>{" ".join([f'<span class="tag">{m}</span>' for m in matches])}</div>
    </div>
    '''
    st.markdown(html_card, unsafe_allow_html=True)
    
    # 移除按鈕 (放在卡片下方)
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code)
        controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
        st.rerun()
