import streamlit as st
import streamlit.components.v1 as components
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
from FinMind.data import DataLoader  # 新增

st.set_page_config(
    page_title="台股看盤-大師強化版",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ══════════════════════════════════════════════════════════
# CSS (完全保留你原本的樣式，僅新增一個閃爍標籤)
# ══════════════════════════════════════════════════════════
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
/* ... 這裡保留你原本所有的 CSS 代碼 ... */
/* 新增：急漲跌閃爍標籤樣式 */
.urgent-tag {
    background: #ef4444; color: white; padding: 2px 8px;
    border-radius: 6px; font-size: 0.65rem; font-weight: 900;
    margin-left: 8px; animation: blink 1.2s infinite;
    vertical-align: middle;
}
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
""" + r"""
/* 由於長度限制，這裡請貼回你原本 app.py 中所有的 CSS 內容 */
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 核心邏輯：LocalStorage 與 Token 管理 (新功能植入)
# ══════════════════════════════════════════════════════════
QP_KEY = "wl"

def inject_localstorage_helper():
    # 擴展後的 JS：同時處理 Watchlist 網址與 FinMind Token
    components.html("""
    <script>
    (function(){
        var LS_URL_KEY = 'twstock_url_v3';
        var LS_TOKEN_KEY = 'fm_token_v3';
        try {
            // 處理網址還原
            if (window.parent.location.search.indexOf('wl=') !== -1) {
                localStorage.setItem(LS_URL_KEY, window.parent.location.href);
            } else {
                var saved = localStorage.getItem(LS_URL_KEY);
                if (saved) { window.parent.history.replaceState({}, '', saved); }
            }
            // 提醒使用者 Token 已儲存 (這部分由 Python text_input 的 value 處理)
        } catch(e) {}
    })();
    </script>
    """, height=0)

# ══════════════════════════════════════════════════════════
# 資料獲取與技術指標 (保留原有的計算邏輯)
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_finmind_data(stock_ids, token):
    if not token: return None
    try:
        dl = DataLoader()
        dl.login(token=token)
        return dl.taiwan_stock_tick_snapshot(stock_ids)
    except: return None

# ... 這裡保留你原本的 fetch_twse_realtime, fetch_yf_hist, calculate_kd, analyze_signal 等函數 ...

def get_stock_data(twse_data, fm_df, stock, threshold):
    code = stock["id"]
    # 1. 基礎資料 (原本的邏輯)
    # ... 保留原本 get_stock_data 的核心邏輯 ...
    
    # 2. 強化：若有 FinMind，覆蓋為更即時的價格與漲跌幅
    is_urgent = ""
    if fm_df is not None and not fm_df.empty:
        match = fm_df[fm_df['stock_id'] == code]
        if not match.empty:
            # 這裡使用 FinMind 的數據
            price = float(match.iloc[0]['last_price'])
            change_pct = float(match.iloc[0]['change_rate'])
            # 急漲跌判定
            if change_pct >= threshold: is_urgent = "⚡ 急漲"
            elif change_pct <= -threshold: is_urgent = "📉 急跌"
            
    # 回傳資料中新增 urgent 欄位
    # ... 回傳原本的所有欄位，並加上 "urgent": is_urgent ...
    return row_dict 

# ══════════════════════════════════════════════════════════
# 主程式：整合 UI
# ══════════════════════════════════════════════════════════

# 側邊欄：新增 API 設定區 (不影響主畫面美觀)
with st.sidebar:
    st.markdown("### 🔑 私人 API 設定")
    user_token = st.text_input("FinMind Token", type="password", help="輸入後可開啟秒級監控")
    if st.button("儲存 Token"):
        components.html(f"<script>localStorage.setItem('fm_token_v3', '{user_token}'); window.parent.location.reload();</script>")
    
    st.divider()
    threshold = st.slider("急漲跌警示門檻 (%)", 0.5, 5.0, 2.0)

# ... 頂部標題、書籤提示、新增股票功能 (完全保留) ...

# 股票清單顯示區
if st.session_state.watchlist:
    ids = [s["id"] for s in st.session_state.watchlist]
    
    # 同時抓取兩種資料源
    fm_df = get_finmind_data(ids, user_token)
    twse_data = fetch_twse_realtime(ids)
    
    for idx, stock in enumerate(st.session_state.watchlist):
        # 傳入 threshold 做判定
        row = get_stock_data(twse_data, fm_df, stock, threshold)
        
        # 修改 render_card：在名稱旁邊加上 row["urgent"] 的顯示
        # 例如：<div class="stock-name">{row["name"]} <span class="urgent-tag">{row["urgent"]}</span></div>
        render_card(row, idx)

# 頁尾更新頻率控制
time.sleep(25) # 為了保護 5 人額度，建議設為 25 秒
st.rerun()
