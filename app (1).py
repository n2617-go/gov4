import streamlit as st
import streamlit.components.v1 as components
import requests
import yfinance as yf
from datetime import datetime
import time
import json
import pandas as pd
from FinMind.data import DataLoader
import urllib3

# 關閉不安全請求的警告訊息（因為我們會用到 verify=False）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股大師-穩定修復版", layout="centered", initial_sidebar_state="collapsed")

DEFAULT_LIST = [
    {"id": "2330", "name": "台積電"},
    {"id": "2317", "name": "鴻海"},
    {"id": "00631L", "name": "元大台灣50正2"},
    {"id": "2002", "name": "中鋼"},
    {"id": "1326", "name": "台化"}
]

if "watchlist" not in st.session_state:
    try:
        url_params = st.query_params.get("wl", "")
        st.session_state.watchlist = json.loads(url_params) if url_params else DEFAULT_LIST
    except:
        st.session_state.watchlist = DEFAULT_LIST

if "fm_token" not in st.session_state:
    st.session_state.fm_token = ""

# ══════════════════════════════════════════════════════════
# 2. 精美 CSS 樣式
# ══════════════════════════════════════════════════════════
st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #0a0d14 !important; color: #e2e8f0 !important; font-family: 'Noto Sans TC', sans-serif !important; }
.stock-card { background: linear-gradient(135deg, #111827 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.08); border-radius: 18px; padding: 1.2rem; margin-bottom: 1rem; border-top: 3px solid #38bdf8; position: relative; }
.up-border { border-top-color: #ef4444 !important; }
.down-border { border-top-color: #22c55e !important; }
.price-main { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; line-height:1; }
.urgent-tag { background: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; animation: blink 1.2s infinite; margin-left: 8px; font-weight:900; }
.urgent-tag.down { background: #22c55e; }
@keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
.tech-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; background: rgba(255,255,255,0.03); border-radius: 10px; padding: 0.6rem; margin-top: 10px; }
.tech-item { text-align: center; font-size: 0.7rem; color: #94a3b8; }
.tech-item b { color: #cbd5e1; font-family: 'JetBrains Mono'; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 3. 核心工具 (加入 SSL 忽略與 Header)
# ══════════════════════════════════════════════════════════

# 模擬真實瀏覽器 Header
REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_clean_zh_name(code):
    manual_map = {"00981A": "統一台股增長", "00982A": "復華台灣大排", "00631L": "元大台灣50正2"}
    if code in manual_map: return manual_map[code]
    try:
        # 修正：加入 verify=False 與 headers
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{code}.tw|otc_{code}.tw&json=1"
        res = requests.get(url, headers=REQ_HEADERS, verify=False, timeout=5).json()
        if res.get("msgArray"):
            return res["msgArray"][0]["n"]
    except: pass
    
    try:
        tk = yf.Ticker(f"{code}.TW")
        name = tk.info.get('longName') or tk.info.get('shortName') or f"股票 {code}"
        return name.replace("UPAMC", "統一").replace("Active ETF", "主動型").strip()
    except:
        return f"股票 {code}"

@st.cache_data(ttl=3600)
def get_tech_data(code):
    try:
        tk = yf.Ticker(f"{code}.TW")
        h = tk.history(period="1mo")
        if h.empty: return 0.0, 0.0, 50, 50, 0, "無資料"
        last_p = h['Close'].iloc[-1]
        prev_p = h['Close'].iloc[-2] if len(h)>1 else last_p
        y_chg = ((last_p - prev_p)/prev_p*100)
        l9, h9 = h['Low'].rolling(9).min(), h['High'].rolling(9).max()
        rsv = 100 * (h['Close'] - l9) / (h9 - l9)
        k, d = 50.0, 50.0
        for v in rsv.fillna(50):
            k = (2/3)*k + (1/3)*v
            d = (2/3)*d + (1/3)*k
        ma20 = h['Close'].rolling(20).mean().iloc[-1]
        return last_p, y_chg, k, d, ma20, "⚖️整理"
    except:
        return 0.0, 0.0, 50, 50, 0, "讀取中"

# ══════════════════════════════════════════════════════════
# 4. 主介面邏輯
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("🔑 監控設定")
    token_input = st.text_input("FinMind Token", type="password", value=st.session_state.fm_token)
    if st.button("儲存 Token"):
        st.session_state.fm_token = token_input
        st.rerun()
    st.divider()
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 2.0)
    if st.button("重置名單"):
        st.query_params.clear()
        st.session_state.watchlist = DEFAULT_LIST
        st.rerun()

st.title("📊 台股大師即時監控")

with st.expander("➕ 新增關注股票"):
    col1, col2 = st.columns([3,1])
    with col1: nid = st.text_input("輸入代碼 (例: 00981A)").strip().upper()
    with col2:
        if st.button("加入"):
            if nid and not any(x['id'] == nid for x in st.session_state.watchlist):
                with st.spinner('搜尋中...'):
                    zh_name = get_clean_zh_name(nid)
                    st.session_state.watchlist.append({"id": nid, "name": zh_name})
                    st.query_params["wl"] = json.dumps(st.session_state.watchlist)
                    st.success(f"✅ 已加入 {zh_name}")
                    time.sleep(1)
                    st.rerun()

# 核心修正：抓取即時資料加入錯誤處理與 verify=False
ids = [x['id'] for x in st.session_state.watchlist]
twse_r = []
if ids:
    try:
        twse_url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={'|'.join([f'tse_{i}.tw|otc_{i}.tw' for i in ids])}&json=1"
        resp = requests.get(twse_url, headers=REQ_HEADERS, verify=False, timeout=5)
        twse_r = resp.json().get("msgArray", [])
    except Exception as e:
        # 如果證交所掛掉，保持 twse_r 為空，讓程式用歷史資料撐著
        twse_r = []

for idx, s in enumerate(st.session_state.watchlist):
    code = s['id']
    y_p, y_c, vk, vd, vma, _ = get_tech_data(code)
    
    # 邏輯判定現價
    msg = next((x for x in twse_r if x.get('c') == code), None)
    if msg:
        price = float(msg.get('z') or msg.get('y', 0))
        yest = float(msg.get('y', 0))
        chg = ((price - yest) / yest * 100) if yest else 0
    else:
        price, chg = y_p, y_c

    vsig = "🔥金叉" if vk > vd and vk < 30 else "⚠️死叉" if vk < vd and vk > 70 else "⚖️整理"
    utag = f'<span class="urgent-tag {"down" if chg < 0 else ""}">{"⚡急漲" if chg > 0 else "📉急跌"}</span>' if abs(chg) >= warn_p else ""

    b_cls = "up-border" if chg > 0 else "down-border" if chg < 0 else ""
    st.markdown(f"""
    <div class="stock-card {b_cls}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-weight:900; font-size:1.1rem;">{s['name']} {utag}</div>
                <div style="font-size:0.75rem; color:#64748b;">{code}.TW</div>
            </div>
            <div style="text-align:right;">
                <div class="price-main">{price:.2f}</div>
                <div style="color:{'#ef4444' if chg > 0 else '#22c55e'}; font-weight:700;">{chg:+.2f}%</div>
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

    if st.button(f"🗑️ 移除 {s['name']}", key=f"del_{code}"):
        st.session_state.watchlist.pop(idx)
        st.query_params["wl"] = json.dumps(st.session_state.watchlist)
        st.rerun()

time.sleep(30)
st.rerun()
