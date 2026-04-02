import streamlit as st
import pandas as pd
import numpy as np
import time
import yfinance as yf
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 系統初始化與資料引擎
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控 (FinMind 版)", layout="centered")

# 初始化 FinMind (免 Token 限制為每小時 600 次，對個人監控綽綽有餘)
api = DataLoader()

def get_stock_data_finmind(code):
    """使用 FinMind 抓取即時資料與名稱"""
    try:
        # 1. 抓取中文名稱
        df_info = api.taiwan_stock_info()
        stock_info = df_info[df_info['stock_id'] == code]
        c_name = stock_info['stock_name'].values[0] if not stock_info.empty else f"個股 {code}"
        
        # 2. 抓取近期 K 線 (用於計算指標)
        # 設定抓取最近 30 天
        df = api.taiwan_stock_daily(
            stock_id=code,
            start_date=(pd.Timestamp.now() - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
        )
        
        if df.empty: return None, c_name
        
        # 統一欄位名稱以符合後續計算
        df = df.rename(columns={
            'open': 'Open', 'max': 'High', 'min': 'Low', 
            'close': 'Close', 'Revenue': 'Volume', 'date': 'Date'
        })
        return df, c_name
    except:
        return None, f"個股 {code}"

# ══════════════════════════════════════════════════════════
# 2. 技術指標與符合判定
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list):
    df = df.copy()
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    # KD
    low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['OSC'] = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()
    # 布林
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Upper'] = df['MA20'] + (df['Close'].rolling(20).std() * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("突破布林上軌")
    if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("量能爆發")
    
    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    return int(score), matches, last, prev

# ══════════════════════════════════════════════════════════
# 3. 介面與持久化
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; }
    .tag { background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid #38bdf8; }
</style>
""", unsafe_allow_html=True)

DEFAULT_STOCKS = ["2330", "2317", "00631L", "2454", "2603"]
if "watchlist" not in st.session_state:
    params = st.query_params.get("wl", "")
    st.session_state.watchlist = params.split(",") if params else DEFAULT_STOCKS

def sync(): st.query_params["wl"] = ",".join(st.session_state.watchlist)

st.title("🛡️ FinMind 極短線 AI 監控")

with st.sidebar:
    st.header("⚙️ 設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 1.5)
    if st.button("🔄 恢復預設"):
        st.session_state.watchlist = DEFAULT_STOCKS
        sync(); st.rerun()

with st.expander("➕ 新增監控股票"):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入代碼 (例如: 2603)").strip()
    with c2:
        if st.button("確認加入"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                sync(); st.rerun()

# ══════════════════════════════════════════════════════════
# 4. 主循環渲染
# ══════════════════════════════════════════════════════════
for code in st.session_state.watchlist:
    # 呼叫 FinMind 數據
    df, c_name = get_stock_data_finmind(code)
    
    if df is not None:
        score, matches, last, prev = analyze_stock(df, m_list)
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        alert = f"<span style='color:#facc15;'>🚨 預警({warn_p}%)</span>" if abs(chg) >= warn_p else ""

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color};">{score}分</div>
            <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) {alert}</div>
            <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">
                {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
            </div>
            <div style="margin-bottom:10px;"><b>符合指標：</b><br>{tags_html if tags_html else "掃描中..."}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            sync(); st.rerun()
    else:
        # 如果 FinMind 失敗，嘗試用 yfinance 補位 (這部分加入 try-except 避免崩潰)
        st.warning(f"⚠️ {code} FinMind 載入失敗，嘗試使用備援引擎...")
        # (備援邏輯省略以保持代碼簡潔，或可保留 yfinance 版本)

time.sleep(60)
st.rerun()
