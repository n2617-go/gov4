import streamlit as st
import pandas as pd
import numpy as np
import time
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 核心資料引擎 (支援自訂 Token)
# ══════════════════════════════════════════════════════════
def get_data_engine(token=None):
    api = DataLoader()
    if token:
        try:
            api.login(token=token)
        except:
            pass
    return api

@st.cache_data(ttl=300)
def fetch_stock_full(code, token, m_list):
    try:
        api = get_data_engine(token)
        # 1. 抓取股票基本資訊 (確保中文名稱)
        df_info = api.taiwan_stock_info()
        target = df_info[df_info['stock_id'] == code]
        c_name = target['stock_name'].values[0] if not target.empty else f"個股 {code}"
        
        # 2. 抓取近期數據 (最近 45 天)
        start_dt = (pd.Timestamp.now() - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
        df = api.taiwan_stock_daily(stock_id=code, start_date=start_dt)
        
        if df.empty: return None, c_name, 50, []
        
        # 欄位標準化
        df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
        
        # 3. 技術指標計算
        # RSI
        diff = df['Close'].diff()
        gain = (diff.where(diff > 0, 0)).rolling(14).mean()
        loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        # KD
        low9, high9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
        rsv = 100 * ((df['Close'] - low9) / (high9 - low9))
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()
        # MACD
        e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
        df['OSC'] = (e12 - e26) - (e12 - e26).ewm(span=9).mean()
        # 布林
        ma20 = df['Close'].rolling(20).mean()
        std20 = df['Close'].rolling(20).std()
        df['Upper'] = ma20 + (std20 * 2)

        last, prev = df.iloc[-1], df.iloc[-2]
        matches = []
        if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
        if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
        if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢突破")
        if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("🌌 突破布林上軌")
        if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("📊 量能爆發")
        
        score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
        return df, c_name, int(score), matches
    except Exception as e:
        return None, f"代碼 {code}", 50, []

# ══════════════════════════════════════════════════════════
# 2. UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; }
    .tag { background: rgba(56, 189, 248, 0.12); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
</style>
""", unsafe_allow_html=True)

# 儲存機制
DEFAULT_STOCKS = ["2330", "2317", "00631L", "2454", "2603"]
if "watchlist" not in st.session_state:
    params = st.query_params.get("wl", "")
    st.session_state.watchlist = params.split(",") if params else DEFAULT_STOCKS

def sync(): st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("🛡️ 台股極短線 AI 全能監控")

# 側邊欄：Token 輸入與指標勾選
with st.sidebar:
    st.header("🔑 個人化設定")
    user_token = st.text_input("FinMind Token (選填)", type="password", help="輸入 Token 可獲得更穩定的資料更新速度")
    st.divider()
    m_list = st.multiselect("啟用分析指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時預警門檻 (%)", 0.5, 5.0, 1.5)
    if st.button("🔄 恢復預設清單"):
        st.session_state.watchlist = DEFAULT_STOCKS
        sync(); st.rerun()

# 新增股票
with st.expander("➕ 新增監控標的", expanded=False):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("代碼").strip()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                sync(); st.rerun()

# 數據渲染
for code in st.session_state.watchlist:
    df, c_name, score, matches = fetch_stock_full(code, user_token, m_list)
    
    if df is not None:
        last, prev = df.iloc[-1], df.iloc[-2]
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        alert = f"<span style='color:#facc15;'>🚨 預警({warn_p}%)</span>" if abs(chg) >= warn_p else ""

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size:1.15rem; font-weight:bold;">{c_name} ({code}) {alert}</div>
            <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:8px 0;">
                {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
            </div>
            <div style="margin-top:5px;"><b>符合指標：</b><br>{tags_html if tags_html else "分析中..."}</div>
            <div style="margin-top:10px; font-size:0.85rem; color:#94a3b8;">
                AI 評點：{ "🔥 多頭排列，強烈建議觀察進場點。" if score >= 70 else "📉 技術面走弱，建議先行減碼觀望。" if score <= 30 else "⚖️ 區間盤整，建議靜待方向突破。" }
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            sync(); st.rerun()
    else:
        st.error(f"❌ {code} 資料獲取失敗，請確認代碼或 Token 是否正確。")

time.sleep(60)
st.rerun()
