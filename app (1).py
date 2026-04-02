import streamlit as st
import streamlit.components.v1 as components
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import urllib.parse
import pandas as pd
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 基礎配置與 Session 初始化 (防止 AttributeError)
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="台股看盤-大師強化版",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 初始化所有必要的 Session State
if "watchlist" not in st.session_state:
    # 優先從網址讀取，若無則預設台積電
    try:
        raw = st.query_params.get("wl", "")
        st.session_state.watchlist = json.loads(raw) if raw else [{"id": "2330", "name": "台積電"}]
    except:
        st.session_state.watchlist = [{"id": "2330", "name": "台積電"}]

if "add_msg" not in st.session_state: st.session_state.add_msg = ""
if "add_type" not in st.session_state: st.session_state.add_type = ""
if "fm_token" not in st.session_state: st.session_state.fm_token = ""

# ══════════════════════════════════════════════════════════
# 2. CSS 樣式 (保留原創設計 + 新增預警標籤)
# ══════════════════════════════════════════════════════════
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0d14 !important;
    color: #e2e8f0 !important;
    font-family: 'Noto Sans TC', sans-serif !important;
}
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 20% 0%, #0f1a2e 0%, #0a0d14 60%) !important;
}
#MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebarNav"] { display: none !important; }

/* 新增：急漲跌閃爍標籤樣式 */
.urgent-tag {
    background: #ef4444; color: white; padding: 2px 8px;
    border-radius: 6px; font-size: 0.65rem; font-weight: 900;
    margin-left: 8px; animation: blink 1.2s infinite;
    vertical-align: middle; box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
}
.urgent-tag.down { background: #22c55e; box-shadow: 0 0 10px rgba(34, 197, 94, 0.5); }
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }

/* 原有美化樣式 */
.app-header { display: flex; align-items: center; justify-content: space-between; padding: 1.5rem 0 1.25rem; border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 1.5rem; }
.app-title { font-size: 1.35rem; font-weight: 900; letter-spacing: -0.02em; color: #f8fafc; }
.app-title span { color: #38bdf8; margin-left: 0.3rem; font-weight: 500; opacity: 0.8; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.07); border-radius: 20px; padding: 1.25rem; margin-bottom: 1rem; position: relative; }
.stock-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--accent, #38bdf8); }
.stock-card.up { --accent: #ef4444; }
.stock-card.down { --accent: #22c55e; }
.price-main { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; color: #f8fafc; line-height: 1.2; }
.up-color { color: #ef4444 !important; }
.down-color { color: #22c55e !important; }
.ohlc-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 12px; padding: 0.75rem; margin-bottom: 1rem; }
.kd-chip { flex: 1; background: rgba(255,255,255,0.04); border-radius: 10px; padding: 0.6rem; text-align: center; border: 1px solid rgba(255,255,255,0.05); }
.remove-btn { color: #475569; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; background: none; border: none; padding: 4px 8px; border-radius: 6px; }
.remove-btn:hover { color: #ef4444; background: rgba(239, 68, 68, 0.1); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 3. 核心功能函數 (整合 FinMind + 原有邏輯)
# ══════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_fm_snapshot(stock_ids, token):
    if not token: return None
    try:
        dl = DataLoader()
        dl.login(token=token)
        return dl.taiwan_stock_tick_snapshot(stock_ids)
    except: return None

def fetch_twse_realtime(stock_ids):
    if not stock_ids: return []
    tse = [f"tse_{sid}.tw" for sid in stock_ids]
    otc = [f"otc_{sid}.tw" for sid in stock_ids]
    ex_ch = "|".join(tse + otc)
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1"
    try:
        res = requests.get(url, timeout=10).json()
        return res.get("msgArray", [])
    except: return []

def calculate_kd(df):
    if len(df) < 9: return 50, 50
    low_9 = df['Low'].rolling(window=9).min()
    high_9 = df['High'].rolling(window=9).max()
    rsv = 100 * (df['Close'] - low_9) / (high_9 - low_9)
    rsv = rsv.fillna(50)
    k, d = 50.0, 50.0
    for val in rsv:
        k = (2/3) * k + (1/3) * val
        d = (2/3) * d + (1/3) * k
    return k, d

def analyze_signal(k, d, price, ma20):
    if k > d and k < 30: return "🔥 超賣區黃金交叉 (看多)"
    if k < d and k > 70: return "⚠️ 超買區死亡交叉 (看空)"
    if price > ma20 and k > d: return "📈 多頭強勢趨勢"
    if price < ma20 and k < d: return "📉 空頭修正趨勢"
    return "⚖️ 區間盤整"

# ══════════════════════════════════════════════════════════
# 4. 側邊欄與 LocalStorage 記憶
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔑 API 設定")
    # 這裡會嘗試抓取 LocalStorage 存過的 Token
    user_token = st.text_input("FinMind Token", type="password", value=st.session_state.fm_token)
    if st.button("儲存 Token 並更新"):
        st.session_state.fm_token = user_token
        components.html(f"<script>localStorage.setItem('fm_token_v3', '{user_token}'); window.parent.location.reload();</script>", height=0)
    
    st.divider()
    threshold = st.slider("急漲跌警示門檻 (%)", 0.5, 5.0, 2.0)
    st.info("💡 只有 5 人使用時，建議更新頻率設為 25-30 秒以節省額度。")

# 網址持久化橋接
components.html("""
<script>
(function(){
    var LS_KEY = 'twstock_url_v3';
    if (window.parent.location.search.indexOf('wl=') !== -1) {
        localStorage.setItem(LS_KEY, window.parent.location.href);
    } else {
        var saved = localStorage.getItem(LS_KEY);
        if (saved) { window.parent.history.replaceState({}, '', saved); }
    }
})();
</script>
""", height=0)

# ══════════════════════════════════════════════════════════
# 5. 主畫面 UI 渲染
# ══════════════════════════════════════════════════════════
now = datetime.now().strftime("%H:%M:%S")
st.markdown(f"""
<div class="app-header">
    <div class="app-title">📊 台股大師<span>即時監控版</span></div>
    <div style="font-family:'JetBrains Mono'; font-size:0.85rem; color:#64748b;">
        <span style="display:inline-block; width:8px; height:8px; background:#22c55e; border-radius:50%; margin-right:5px;"></span>
        LIVE: {now}
    </div>
</div>
""", unsafe_allow_html=True)

# --- 新增功能區 ---
with st.expander("➕ 新增關注股票"):
    col1, col2 = st.columns([3, 1])
    with col1: cid = st.text_input("代號", placeholder="例如: 2330").strip()
    with col2: 
        if st.button("加入清單", use_container_width=True):
            if any(s['id'] == cid for s in st.session_state.watchlist):
                st.session_state.add_msg = "此代碼已在清單中"
                st.session_state.add_type = "err"
            else:
                try:
                    t = yf.Ticker(f"{cid}.TW")
                    name = t.info.get('shortName', cid)
                    st.session_state.watchlist.append({"id": cid, "name": name})
                    st.query_params["wl"] = json.dumps(st.session_state.watchlist)
                    st.session_state.add_msg = f"✅ 已加入 {name}"
                    st.session_state.add_type = "ok"
                    st.rerun()
                except:
                    st.session_state.add_msg = "代碼無效"
                    st.session_state.add_type = "err"

# --- 股票清單渲染 ---
if st.session_state.watchlist:
    ids = [s["id"] for s in st.session_state.watchlist]
    fm_df = get_fm_snapshot(ids, user_token)
    twse_list = fetch_twse_realtime(ids)

    for idx, s in enumerate(st.session_state.watchlist):
        code = s["id"]
        # 初始化數據
        price, chg, open_p, high_p, low_p, yesterday = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        urgent_label = ""

        # 1. 優先從 FinMind 獲取快照 (解決延遲)
        if fm_df is not None and not fm_df.empty:
            m = fm_df[fm_df['stock_id'] == code]
            if not m.empty:
                price = float(m.iloc[0]['last_price'])
                chg = float(m.iloc[0]['change_rate'])
                if chg >= threshold: urgent_label = '<span class="urgent-tag">⚡ 急漲</span>'
                elif chg <= -threshold: urgent_label = '<span class="urgent-tag down">📉 急跌</span>'

        # 2. 備援從 TWSE 獲取
        if price == 0.0:
            msg = next((x for x in twse_list if x.get('c') == code), None)
            if msg:
                price = float(msg.get('z') or msg.get('b', '0').split('_')[0])
                yesterday = float(msg.get('y', 0))
                chg = ((price - yesterday) / yesterday * 100) if yesterday else 0
                open_p, high_p, low_p = float(msg.get('o', 0)), float(msg.get('h', 0)), float(msg.get('l', 0))

        # 3. yfinance 獲取歷史與技術指標
        tk = yf.Ticker(f"{code}.TW")
        hist = tk.history(period="1mo")
        k, d, signal = 50, 50, "計算中..."
        if not hist.empty:
            k, d = calculate_kd(hist)
            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            signal = analyze_signal(k, d, price, ma20)

        # 渲染卡片
        color_class = "up" if chg > 0 else "down"
        txt_color = "up-color" if chg > 0 else "down-color"
        
        st.markdown(f"""
        <div class="stock-card {color_class}">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem;">
                <div>
                    <div style="font-size:1.1rem; font-weight:900;">{s['name']} {urgent_label}</div>
                    <div style="font-size:0.75rem; color:#64748b; font-family:'JetBrains Mono';">{code} · TAIWAN</div>
                </div>
                <div style="text-align:right;">
                    <div class="price-main">{price:.2f}</div>
                    <div class="price-change {txt_color}" style="font-family:'JetBrains Mono'; font-weight:700;">
                        {'▲' if chg > 0 else '▼'} {abs(chg):.2f}%
                    </div>
                </div>
            </div>
            <div class="ohlc-row">
                <div style="text-align:center;"><div style="font-size:0.6rem; color:#64748b; margin-bottom:2px;">K值</div><div class="ohlc-val">{k:.1f}</div></div>
                <div style="text-align:center;"><div style="font-size:0.6rem; color:#64748b; margin-bottom:2px;">D值</div><div class="ohlc-val">{d:.1f}</div></div>
                <div style="text-align:center;"><div style="font-size:0.6rem; color:#64748b; margin-bottom:2px;">開盤</div><div class="ohlc-val">{open_p:.1f}</div></div>
                <div style="text-align:center;"><div style="font-size:0.6rem; color:#64748b; margin-bottom:2px;">最高</div><div class="ohlc-val">{high_p:.1f}</div></div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="font-size:0.75rem; font-weight:700; color:#38bdf8;">{signal}</div>
                <form action="/" method="get">
                    <button class="remove-btn" name="remove" value="{idx}">移除</button>
                </form>
            </div>
        </div>
        """, unsafe_allow_html=True)

# 處理移除邏輯
if st.query_params.get("remove"):
    ridx = int(st.query_params.get("remove"))
    st.session_state.watchlist.pop(ridx)
    st.query_params["wl"] = json.dumps(st.session_state.watchlist)
    st.rerun()

# ══════════════════════════════════════════════════════════
# 6. 自動重新整理控制
# ══════════════════════════════════════════════════════════
time.sleep(25)
st.rerun()
