import streamlit as st
import pandas as pd
import numpy as np
import time
import requests
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心 API 抓取 (加入自動日期回溯機制)
# ══════════════════════════════════════════════════════════
def fetch_finmind_api(dataset, stock_id, token, days=45):
    url = "https://api.finmindtrade.com/api/v4/data"
    
    # 計算起始日期 (確保涵蓋最近的交易日)
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "token": token,
        "start_date": start_date
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        if res.status_code != 200:
            return pd.DataFrame()
            
        data = res.json()
        if data.get("msg") == "success" and len(data.get("data", [])) > 0:
            df = pd.DataFrame(data["data"])
            # 確保日期格式正確並排序
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def analyze_stock(df, m_list):
    df = df.copy()
    # 轉換 FinMind 原始欄位為技術分析慣用名稱
    df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
    
    if len(df) < 15:
        return 50, [], df.iloc[-1], df.iloc[-2]

    # RSI (14)
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
# 2. UI 設定
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

# 登入驗證
if not st.session_state.auth:
    st.title("🛡️ 專業版授權驗證")
    t_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("開啟 AI 監控系統", use_container_width=True):
        check = fetch_finmind_api("TaiwanStockInfo", "2330", t_input)
        if not check.empty:
            st.session_state.tk = t_input
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("❌ Token 驗證失敗，請確認 Token 正確性。")
    st.stop()

# ══════════════════════════════════════════════════════════
# 3. 主面板
# ══════════════════════════════════════════════════════════
st.title("⚡ AI 自動監控中")

with st.sidebar:
    st.header("⚙️ 控制項")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警比例 (%)", 0.5, 5.0, 1.5)
    if st.button("🚪 更換 Token"):
        st.session_state.auth = False
        st.rerun()

# 名稱快取
@st.cache_data(ttl=3600)
def get_name_map(token):
    df = fetch_finmind_api("TaiwanStockInfo", "", token)
    return dict(zip(df['stock_id'], df['stock_name'])) if not df.empty else {}

name_map = get_name_map(st.session_state.tk)

# 卡片渲染
for code in st.session_state.watchlist:
    # 抓取最近 45 天資料，確保無論何時都能抓到最後一個交易日
    df = fetch_finmind_api("TaiwanStockDaily", code, st.session_state.tk)
    
    if not df.empty and len(df) >= 2:
        c_name = name_map.get(code, f"個股 {code}")
        score, matches, last, prev = analyze_stock(df, m_list)
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        
        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        last_date = last['date'].strftime('%m/%d')
        alert = f"<span style='color:#facc15;'>🚨 預警</span>" if abs(chg) >= warn_p else ""

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size:1rem; font-weight:bold;">{c_name} ({code}) {alert} <span style="font-size:0.7rem; color:#94a3b8;">[{last_date}]</span></div>
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
        st.error(f"❌ {code}: API 暫無回傳資料，請稍後再試。")

time.sleep(60)
st.rerun()
