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
st.set_page_config(page_title="台股大師-終極穩定版", layout="centered", initial_sidebar_state="collapsed")

if "watchlist" not in st.session_state:
    st.session_state.watchlist = [{"id": "2330", "name": "台積電"}]
if "add_msg" not in st.session_state: st.session_state.add_msg = ""
if "fm_token" not in st.session_state: st.session_state.fm_token = ""

# ══════════════════════════════════════════════════════════
# 2. CSS 樣式
# ══════════════════════════════════════════════════════════
st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #0a0d14 !important; color: #e2e8f0 !important; font-family: 'Noto Sans TC', sans-serif !important; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.07); border-radius: 20px; padding: 1.25rem; margin-bottom: 1rem; border-top: 3px solid #38bdf8; }
.price-main { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; }
.urgent-tag { background: #ef4444; color: white; padding: 2px 8px; border-radius: 6px; font-size: 0.65rem; animation: blink 1.2s infinite; margin-left: 8px; }
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
.ohlc-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 0.75rem; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 3. 核心功能 (加入更強的錯誤容忍)
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def get_fm_snapshot(stock_ids, token):
    if not token: return None
    try:
        dl = DataLoader()
        dl.login(token=token)
        return dl.taiwan_stock_tick_snapshot(stock_ids)
    except: return None

@st.cache_data(ttl=3600) # 歷史資料快取一小時
def get_technical_data(code):
    # 預設回傳值，防止 Yahoo 封鎖時導致網頁全白
    default = {"k": 50.0, "d": 50.0, "sig": "連線受限", "ma20": 0.0}
    try:
        tk = yf.Ticker(f"{code}.TW")
        hist = tk.history(period="1mo")
        if hist.empty: return default
        
        low_9 = hist['Low'].rolling(window=9).min()
        high_9 = hist['High'].rolling(window=9).max()
        rsv = 100 * (hist['Close'] - low_9) / (high_9 - low_9)
        rsv = rsv.fillna(50)
        k, d = 50.0, 50.0
        for val in rsv:
            k = (2/3) * k + (1/3) * val
            d = (2/3) * d + (1/3) * k
        
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        sig = "🔥 低檔金叉" if k > d and k < 30 else "⚠️ 高檔死叉" if k < d and k > 70 else "⚖️ 區間整理"
        return {"k": k, "d": d, "sig": sig, "ma20": ma20}
    except:
        return default

def fetch_twse_live(stock_ids):
    if not stock_ids: return []
    try:
        ex_ch = "|".join([f"tse_{sid}.tw" for sid in stock_ids] + [f"otc_{sid}.tw" for sid in stock_ids])
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1"
        return requests.get(url, timeout=5).json().get("msgArray", [])
    except: return []

# ══════════════════════════════════════════════════════════
# 4. 主介面
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔑 API 設定")
    user_token = st.text_input("FinMind Token", type="password", value=st.session_state.fm_token)
    if st.button("儲存並啟動"):
        st.session_state.fm_token = user_token
        components.html(f"<script>localStorage.setItem('fm_token_v3', '{user_token}'); window.parent.location.reload();</script>", height=0)
    threshold = st.slider("預警門檻 (%)", 0.5, 5.0, 2.0)

# --- 新增股票邏輯 (修正版) ---
with st.expander("➕ 新增關注股票"):
    cid = st.text_input("輸入股票代號 (例: 2454)").strip()
    if st.button("確認加入"):
        if cid:
            try:
                # 為了避免新增時被 Yahoo 封鎖，我們改用簡單的提示，不強制去抓 Info
                st.session_state.watchlist.append({"id": cid, "name": f"股票 {cid}"})
                st.success(f"已加入 {cid} 到清單！")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error("加入失敗，請稍後再試")

# --- 顯示清單 ---
ids = [s["id"] for s in st.session_state.watchlist]
fm_df = get_fm_snapshot(ids, user_token)
twse_list = fetch_twse_live(ids)

for s in st.session_state.watchlist:
    code = s["id"]
    price, chg, urgent_tag = 0.0, 0.0, ""
    
    # 1. 即時價格 (優先 FinMind)
    if fm_df is not None and not fm_df.empty:
        m = fm_df[fm_df['stock_id'] == code]
        if not m.empty:
            price = float(m.iloc[0]['last_price'])
            chg = float(m.iloc[0]['change_rate'])
            if abs(chg) >= threshold:
                urgent_tag = f'<span class="urgent-tag">{"⚡ 急漲" if chg > 0 else "📉 急跌"}</span>'

    # 2. 備援價格 (TWSE)
    if price == 0.0:
        msg = next((x for x in twse_list if x.get('c') == code), None)
        if msg:
            price = float(msg.get('z') or msg.get('y', 0))
            yest = float(msg.get('y', 0))
            chg = ((price - yest) / yest * 100) if yest else 0

    # 3. 技術指標
    tech = get_technical_data(code)

    # 4. 渲染卡片
    st.markdown(f"""
    <div class="stock-card">
        <div style="display:flex; justify-content:space-between;">
            <div>
                <div style="font-size:1.2rem; font-weight:900;">{s['name']} {urgent_tag}</div>
                <div style="color:#64748b; font-size:0.8rem;">{code}</div>
            </div>
            <div style="text-align:right;">
                <div class="price-main">{price:.2f}</div>
                <div style="color:{'#ef4444' if chg > 0 else '#22c55e'}; font-weight:700;">{chg:+.2f}%</div>
            </div>
        </div>
        <div class="ohlc-row">
            <div style="text-align:center;"><small>K值</small><br><b>{tech['k']:.1f}</b></div>
            <div style="text-align:center;"><small>D值</small><br><b>{tech['d']:.1f}</b></div>
            <div style="text-align:center;"><small>MA20</small><br><b>{tech['ma20']:.1f}</b></div>
            <div style="text-align:center;"><small>訊號</small><br><b>{tech['sig']}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

time.sleep(30)
st.rerun()
