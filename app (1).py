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
# 1. 系統初始化與預設清單
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股監控-專業優化版", layout="centered", initial_sidebar_state="collapsed")

# 預設五檔股票清單
DEFAULT_LIST = [
    {"id": "2330", "name": "台積電"},
    {"id": "2317", "name": "鴻海"},
    {"id": "00631L", "name": "元大台灣50正2"},
    {"id": "2002", "name": "中鋼"},
    {"id": "1326", "name": "台化"}
]

if "watchlist" not in st.session_state:
    st.session_state.watchlist = DEFAULT_LIST
if "fm_token" not in st.session_state:
    st.session_state.fm_token = ""

# ══════════════════════════════════════════════════════════
# 2. 精簡版核心 CSS
# ══════════════════════════════════════════════════════════
st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #0a0d14 !important; color: #e2e8f0 !important; font-family: 'Noto Sans TC', sans-serif !important; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 1.2rem; margin-bottom: 1rem; border-top: 3px solid #38bdf8; }
.up-border { border-top-color: #ef4444 !important; }
.down-border { border-top-color: #22c55e !important; }
.price-main { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; color: #f8fafc; line-height:1; }
.urgent-tag { background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; animation: blink 1.2s infinite; margin-left: 8px; font-weight:900; }
.urgent-tag.down { background: #22c55e; }
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
.tech-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 10px; padding: 0.6rem; margin-top: 10px; }
.tech-item { text-align: center; font-size: 0.7rem; color: #94a3b8; }
.tech-item b { color: #cbd5e1; font-family: 'JetBrains Mono'; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 3. 高效能資料抓取 (包含三層救急邏輯)
# ══════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def get_fm_data(stock_ids, token):
    """第一層：FinMind 秒級監控"""
    if not token: return None
    try:
        dl = DataLoader()
        dl.login(token=token)
        return dl.taiwan_stock_tick_snapshot(stock_ids)
    except: return None

def get_twse_live(ids):
    """第二層：證交所 API 備援"""
    try:
        ex = "|".join([f"tse_{i}.tw" for i in ids] + [f"otc_{i}.tw" for i in ids])
        r = requests.get(f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex}&json=1", timeout=3)
        return r.json().get("msgArray", [])
    except: return []

@st.cache_data(ttl=3600)
def get_fallback_price_and_tech(code):
    """第三層：Yahoo 歷史資料 (最終保險)"""
    try:
        tk = yf.Ticker(f"{code}.TW" if not code.startswith('00') else f"{code}.TW")
        h = tk.history(period="1mo")
        if h.empty: return 0.0, 0.0, 50, 50, 0, "無資料"
        
        last_price = h['Close'].iloc[-1]
        prev_price = h['Close'].iloc[-2] if len(h) > 1 else last_price
        yest_chg = ((last_price - prev_price) / prev_price * 100)
        
        # KD 計算
        l9, h9 = h['Low'].rolling(9).min(), h['High'].rolling(9).max()
        rsv = 100 * (h['Close'] - l9) / (h9 - l9)
        k, d = 50.0, 50.0
        for v in rsv.fillna(50):
            k = (2/3)*k + (1/3)*v
            d = (2/3)*d + (1/3)*k
        ma20 = h['Close'].rolling(20).mean().iloc[-1]
        sig = "🔥金叉" if k > d and k < 30 else "⚠️死叉" if k < d and k > 70 else "⚖️整理"
        
        return last_price, yest_chg, k, d, ma20, sig
    except:
        return 0.0, 0.0, 50, 50, 0, "連線中"

# ══════════════════════════════════════════════════════════
# 4. UI 邏輯
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔑 監控設定")
    token_input = st.text_input("FinMind Token", type="password", value=st.session_state.fm_token)
    if st.button("儲存並套用"):
        st.session_state.fm_token = token_input
        st.rerun()
    st.divider()
    warn_p = st.slider("急漲跌警示門檻 (%)", 0.5, 5.0, 2.0)
    if st.button("重置為預設清單"):
        st.session_state.watchlist = DEFAULT_LIST
        st.rerun()

st.markdown(f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;"><h3>📊 台股大師即時監控</h3><code style="color:#64748b;">{datetime.now().strftime("%H:%M:%S")}</code></div>', unsafe_allow_html=True)

with st.expander("➕ 新增股票"):
    col1, col2 = st.columns([3,1])
    with col1: new_id = st.text_input("輸入代碼 (例: 2317)").strip()
    with col2:
        if st.button("加入"):
            if new_id and not any(x['id'] == new_id for x in st.session_state.watchlist):
                st.session_state.watchlist.append({"id": new_id, "name": f"股票 {new_id}"})
                st.rerun()

# --- 核心監控循環 ---
ids = [x['id'] for x in st.session_state.watchlist]
fm_df = get_fm_data(ids, st.session_state.fm_token)
twse_data = get_twse_live(ids)

for s in st.session_state.watchlist:
    code = s['id']
    price, chg, utag = 0.0, 0.0, ""
    
    # 取得歷史技術指標 (與價格分離，確保不影響即時性)
    y_price, y_chg, vk, vd, vma, vsig = get_fallback_price_and_tech(code)

    # 1. 抓即時價 (優先 FinMind)
    if fm_df is not None and not fm_df.empty:
        m = fm_df[fm_df['stock_id'] == code]
        if not m.empty:
            price = float(m.iloc[0]['last_price'])
            chg = float(m.iloc[0]['change_rate'])

    # 2. 備援 (TWSE)
    if price == 0.0:
        msg = next((x for x in twse_data if x.get('c') == code), None)
        if msg:
            price = float(msg.get('z') or msg.get('y', 0))
            yest = float(msg.get('y', 0))
            chg = ((price - yest) / yest * 100) if yest else 0
    
    # 3. 終極備援 (Yahoo 歷史最後一筆)
    if price == 0.0:
        price, chg = y_price, y_chg

    # 判定警示
    if abs(chg) >= warn_p:
        utag = f'<span class="urgent-tag {"down" if chg < 0 else ""}">{"⚡急漲" if chg > 0 else "📉急跌"}</span>'

    # 4. 渲染卡片
    border_cls = "up-border" if chg > 0 else "down-border" if chg < 0 else ""
    st.markdown(f"""
    <div class="stock-card {border_cls}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-weight:900; font-size:1.1rem;">{s['name']} {utag}</div>
                <div style="font-size:0.75rem; color:#64748b; font-family:JetBrains Mono;">{code}.TW</div>
            </div>
            <div style="text-align:right;">
                <div class="price-main">{price:.2f}</div>
                <div style="color:{'#ef4444' if chg > 0 else '#22c55e'}; font-weight:700; font-size:0.9rem;">{chg:+.2f}%</div>
            </div>
        </div>
        <div class="tech-row">
            <div class="tech-item">K值<br><b>{vk:.1f}</b></div>
            <div class="tech-item">D值<br><b>{vd:.1f}</b></div>
            <div class="tech-item">MA20<br><b>{vma:.1f}</b></div>
            <div class="tech-item">訊號<br><b>{vsig}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# 刷新控制
time.sleep(30)
st.rerun()
