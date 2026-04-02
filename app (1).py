import streamlit as st
import streamlit.components.v1 as components
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 基礎配置與 Session 初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="台股大師-穩定監控版",
    layout="centered",
    initial_sidebar_state="collapsed"
)

if "watchlist" not in st.session_state:
    try:
        raw = st.query_params.get("wl", "")
        st.session_state.watchlist = json.loads(raw) if raw else [{"id": "2330", "name": "台積電"}]
    except:
        st.session_state.watchlist = [{"id": "2330", "name": "台積電"}]

if "fm_token" not in st.session_state: st.session_state.fm_token = ""

# ══════════════════════════════════════════════════════════
# 2. CSS 樣式 (包含閃爍標籤)
# ══════════════════════════════════════════════════════════
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
html, body, [data-testid="stAppViewContainer"] {
    background: #0a0d14 !important;
    color: #e2e8f0 !important;
    font-family: 'Noto Sans TC', sans-serif !important;
}
.urgent-tag {
    background: #ef4444; color: white; padding: 2px 8px; border-radius: 6px; 
    font-size: 0.65rem; font-weight: 900; margin-left: 8px; 
    animation: blink 1.2s infinite; vertical-align: middle;
}
.urgent-tag.down { background: #22c55e; }
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
.app-header { display: flex; align-items: center; justify-content: space-between; padding: 1.5rem 0; border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 1.5rem; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.07); border-radius: 20px; padding: 1.25rem; margin-bottom: 1rem; position: relative; }
.stock-card.up { border-top: 3px solid #ef4444; }
.stock-card.down { border-top: 3px solid #22c55e; }
.price-main { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; }
.up-color { color: #ef4444; }
.down-color { color: #22c55e; }
.ohlc-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 0.75rem; margin-top: 10px; }
.ohlc-val { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #cbd5e1; text-align: center;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 3. 核心功能函數 (修復 RateLimit 重點：加強快取)
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300) # 即時快照每 5 分鐘過期
def get_fm_snapshot(stock_ids, token):
    if not token: return None
    try:
        dl = DataLoader()
        dl.login(token=token)
        return dl.taiwan_stock_tick_snapshot(stock_ids)
    except: return None

@st.cache_data(ttl=3600) # 歷史資料與 KD 每 1 小時才去問一次 Yahoo，徹底解決 Rate Limit
def get_technical_indicators(code):
    try:
        tk = yf.Ticker(f"{code}.TW")
        hist = tk.history(period="1mo")
        if hist.empty: return 50, 50, "資料不足", 0.0
        
        # KD 計算
        low_9 = hist['Low'].rolling(window=9).min()
        high_9 = hist['High'].rolling(window=9).max()
        rsv = 100 * (hist['Close'] - low_9) / (high_9 - low_9)
        rsv = rsv.fillna(50)
        k, d = 50.0, 50.0
        for val in rsv:
            k = (2/3) * k + (1/3) * val
            d = (2/3) * d + (1/3) * k
        
        # 簡單訊號
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        price_now = hist['Close'].iloc[-1]
        if k > d and k < 30: sig = "🔥 低檔金叉"
        elif k < d and k > 70: sig = "⚠️ 高檔死叉"
        else: sig = "⚖️ 區間整理"
        
        return k, d, sig, ma20
    except:
        return 50, 50, "查詢受限", 0.0

def fetch_twse_backup(stock_ids):
    if not stock_ids: return []
    try:
        ex_ch = "|".join([f"tse_{sid}.tw" for sid in stock_ids] + [f"otc_{sid}.tw" for sid in stock_ids])
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1"
        return requests.get(url, timeout=10).json().get("msgArray", [])
    except: return []

# ══════════════════════════════════════════════════════════
# 4. 側邊欄與 LocalStorage
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔑 API 設定")
    user_token = st.text_input("FinMind Token", type="password", value=st.session_state.fm_token)
    if st.button("儲存 Token"):
        st.session_state.fm_token = user_token
        components.html(f"<script>localStorage.setItem('fm_token_v3', '{user_token}'); window.parent.location.reload();</script>", height=0)
    
    threshold = st.slider("急漲跌警示門檻 (%)", 0.5, 5.0, 2.0)
    st.warning("⚠️ 若出現 RateLimit 錯誤，請等待 10 分鐘讓 Yahoo 解封。")

# ══════════════════════════════════════════════════════════
# 5. 主畫面渲染
# ══════════════════════════════════════════════════════════
st.markdown(f'<div class="app-header"><div class="app-title">📊 台股大師<span>即時監控版</span></div><div style="font-size:0.8rem; color:#64748b;">LIVE: {datetime.now().strftime("%H:%M:%S")}</div></div>', unsafe_allow_html=True)

# 股票清單處理
if st.session_state.watchlist:
    ids = [s["id"] for s in st.session_state.watchlist]
    fm_df = get_fm_snapshot(ids, user_token)
    twse_list = fetch_twse_backup(ids)

    for idx, s in enumerate(st.session_state.watchlist):
        code = s["id"]
        price, chg, urgent_html = 0.0, 0.0, ""

        # 1. 抓取即時數據 (優先用 FinMind)
        if fm_df is not None and not fm_df.empty:
            m = fm_df[fm_df['stock_id'] == code]
            if not m.empty:
                price = float(m.iloc[0]['last_price'])
                chg = float(m.iloc[0]['change_rate'])
                if chg >= threshold: urgent_html = '<span class="urgent-tag">⚡ 急漲</span>'
                elif chg <= -threshold: urgent_html = '<span class="urgent-tag down">📉 急跌</span>'
        
        # 2. 備援 (TWSE)
        if price == 0.0:
            msg = next((x for x in twse_list if x.get('c') == code), None)
            if msg:
                price = float(msg.get('z') or msg.get('b', '0').split('_')[0])
                yest = float(msg.get('y', 0))
                chg = ((price - yest) / yest * 100) if yest else 0

        # 3. 技術指標 (使用強效快取函數)
        k, d, signal, ma20 = get_technical_indicators(code)

        # 4. 渲染
        color_class = "up" if chg > 0 else "down"
        txt_color = "up-color" if chg > 0 else "down-color"
        
        st.markdown(f"""
        <div class="stock-card {color_class}">
            <div style="display:flex; justify-content:space-between;">
                <div>
                    <div style="font-size:1.1rem; font-weight:900;">{s['name']} {urgent_html}</div>
                    <div style="font-size:0.7rem; color:#64748b;">{code} · TAIWAN</div>
                </div>
                <div style="text-align:right;">
                    <div class="price-main">{price:.2f}</div>
                    <div class="price-change {txt_color}" style="font-weight:700;">{chg:+.2f}%</div>
                </div>
            </div>
            <div class="ohlc-row">
                <div class="ohlc-val"><div style="color:#64748b; font-size:0.6rem;">K值</div>{k:.1f}</div>
                <div class="ohlc-val"><div style="color:#64748b; font-size:0.6rem;">D值</div>{d:.1f}</div>
                <div class="ohlc-val"><div style="color:#64748b; font-size:0.6rem;">MA20</div>{ma20:.1f}</div>
                <div class="ohlc-val"><div style="color:#64748b; font-size:0.6rem;">訊號</div>{signal}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# 刷新控制
time.sleep(30) # 增加到 30 秒，進一步降低請求頻率
st.rerun()
