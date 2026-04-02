import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心 API 抓取 (改用官方最穩定的參數格式)
# ══════════════════════════════════════════════════════════
def fetch_finmind_api(dataset, data_id, token, days=50):
    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # 這裡的參數名稱必須完全精確
    params = {
        "dataset": dataset,
        "data_id": data_id,
        "start_date": start_date,
        "token": token
    }
    
    try:
        # 加入更完整的 Header 模擬
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        }
        res = requests.get(url, params=params, headers=headers, timeout=15)
        
        if res.status_code != 200:
            return pd.DataFrame(), f"HTTP Error {res.status_code}"
            
        result = res.json()
        if result.get("msg") == "success" and len(result.get("data", [])) > 0:
            df = pd.DataFrame(result["data"])
            return df, "success"
        else:
            # 回傳錯誤訊息幫助除錯
            return pd.DataFrame(), result.get("msg", "No Data")
    except Exception as e:
        return pd.DataFrame(), str(e)

def analyze_stock(df, m_list):
    df = df.copy()
    # FinMind 欄位轉換
    df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
    
    # RSI
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.00001))))
    
    # KD
    low9, high9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low9) / (high9 - low9 + 0.00001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # MACD
    e12 = df['Close'].ewm(span=12, adjust=False).mean()
    e26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['OSC'] = (e12 - e26) - (e12 - e26).ewm(span=9, adjust=False).mean()
    
    # 布林
    ma20 = df['Close'].rolling(20).mean()
    df['Upper'] = ma20 + (df['Close'].rolling(20).std() * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("📊 量能爆發")
    
    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    return int(score), matches, last, prev

# ══════════════════════════════════════════════════════════
# 2. 介面設定
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border: 1px solid rgba(255,255,255,0.05); }
    .tag { background: rgba(56, 189, 248, 0.12); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
</style>
""", unsafe_allow_html=True)

if "auth" not in st.session_state: st.session_state.auth = False
if "tk" not in st.session_state: st.session_state.tk = ""
if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

# 登入牆
if not st.session_state.auth:
    st.title("🛡️ 專業版授權驗證")
    t_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("開啟 AI 監控", use_container_width=True):
        # 測試抓取股票資訊集
        test_df, msg = fetch_finmind_api("TaiwanStockInfo", "2330", t_input)
        if not test_df.empty:
            st.session_state.tk = t_input
            st.session_state.auth = True
            st.rerun()
        else:
            st.error(f"❌ 驗證失敗。訊息：{msg}")
    st.stop()

# ══════════════════════════════════════════════════════════
# 3. 監控主畫面
# ══════════════════════════════════════════════════════════
st.title("⚡ AI 自動監控中")

with st.sidebar:
    st.header("⚙️ 設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警比例 (%)", 0.5, 5.0, 1.5)
    if st.button("🚪 登出系統"):
        st.session_state.auth = False
        st.rerun()

# 名稱快取
@st.cache_data(ttl=3600)
def get_name_map(token):
    df, _ = fetch_finmind_api("TaiwanStockInfo", "", token)
    return dict(zip(df['stock_id'], df['stock_name'])) if not df.empty else {}

name_map = get_name_map(st.session_state.tk)

# 渲染卡片
for code in st.session_state.watchlist:
    # 抓取日 K
    df, msg = fetch_finmind_api("TaiwanStockDaily", code, st.session_state.tk)
    
    if not df.empty and len(df) >= 2:
        c_name = name_map.get(code, f"個股 {code}")
        score, matches, last, prev = analyze_stock(df, m_list)
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        
        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        last_date = str(last['date'])[:10]

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size:1rem; font-weight:bold;">{c_name} ({code}) <span style="font-size:0.7rem; color:#94a3b8;">[{last_date}]</span></div>
            <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">
                {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
            </div>
            <div><b>符合指標：</b><br>{tags_html if tags_html else "無觸發"}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            st.rerun()
    else:
        # Debug 資訊顯示在警告內
        st.warning(f"⚠️ {code}: 抓取失敗 ({msg})")

time.sleep(60)
st.rerun()
