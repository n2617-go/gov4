
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

# 務必給 Cookie 一點讀取時間，或使用 session_state 緩存
cookie_watchlist = controller.get('user_watchlist')
cookie_token = controller.get('finmind_token')

if "watchlist" not in st.session_state:
    if cookie_watchlist:
        try:
            # 確保從 Cookie 讀取的是 List
            st.session_state.watchlist = json.loads(cookie_watchlist)
        except:
            st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
    else:
        st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 數據與分析函式 (保持先前穩定的邏輯)
# ══════════════════════════════════════════════════════════
def get_smart_data(code):
    yf_code = code + ".TW" if len(code) <= 4 else code + ".TWO"
    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period="3mo")
        if not df.empty:
            info = ticker.info
            name = info.get('longName') or info.get('shortName') or f"個股 {code}"
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return df.rename(columns={'high':'max', 'low':'min'}), name
    except: pass
    return pd.DataFrame(), code

def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20: return 50, [], "數據不足", "累積中", "觀望", False
    # ... (指標計算邏輯同前，省略以簡化) ...
    # 假設回傳 score, matches, status, reason, strategy, is_warn
    return 60, ["🔥 範例指標"], "觀察中", "目前趨勢穩定。", "續抱", False

# ══════════════════════════════════════════════════════════
# 3. UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控", layout="centered")

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 設定中心")
    m_list = st.multiselect("指標", ["KD", "MACD", "RSI", "布林", "成交量"], default=["KD", "MACD", "RSI"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    
    st.divider()
    new_code = st.text_input("➕ 新增代碼")
    if st.button("確認新增"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            # 存入 Cookie
            controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
            st.success(f"已新增 {new_code}")
            time.sleep(0.5)
            st.rerun()

# 主畫面
st.title("⚡ AI 自動監控面板")

# 使用 list(st.session_state.watchlist) 避免在迴圈中更動列表導致報錯
for code in list(st.session_state.watchlist):
    df, c_name = get_smart_data(code)
    if df.empty: continue
    
    # 呼叫分析
    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    
    # 渲染卡片 (HTML 部分...)
    st.markdown(f"### {c_name} ({code}) - {status}")
    
    # --- 關鍵修正：將移除按鈕放在迴圈內，並使用唯一的 key ---
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code)
        # 同步更新 Cookie
        controller.set('user_watchlist', json.dumps(st.session_state.watchlist), max_age=2592000)
        st.toast(f"已移除 {code}")
        time.sleep(0.5)
        st.rerun()
    st.divider()
