import streamlit as st
import pandas as pd
import numpy as np
import time
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 核心邏輯：技術指標計算
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list):
    df = df.copy()
    # 欄位標準化 (FinMind 原始欄位為小寫)
    df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
    
    # RSI (14)
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss + 0.00001)))
    
    # KD (9, 3, 3)
    low9, high9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low9) / (high9 - low9 + 0.00001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # MACD
    e12 = df['Close'].ewm(span=12, adjust=False).mean()
    e26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = e12 - e26
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['OSC'] = df['DIF'] - df['DEA']
    
    # 布林通道
    df['MA20'] = df['Close'].rolling(20).mean()
    df['STD'] = df['Close'].rolling(20).std()
    df['Upper'] = df['MA20'] + (df['STD'] * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("📊 量能爆發")
    
    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    return int(score), matches, last, prev

# ══════════════════════════════════════════════════════════
# 2. UI 介面與樣式
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border: 1px solid rgba(255,255,255,0.05); }
    .tag { background: rgba(56, 189, 248, 0.12); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
    .auth-container { background: #1e293b; padding: 40px; border-radius: 15px; border: 1px solid #334155; margin-top: 50px; }
</style>
""", unsafe_allow_html=True)

# Session State 初始化
if "auth_status" not in st.session_state: st.session_state.auth_status = False
if "api_token" not in st.session_state: st.session_state.api_token = ""
if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "00631L", "2454", "2603"]

# ══════════════════════════════════════════════════════════
# 3. 登入門檻
# ══════════════════════════════════════════════════════════
if not st.session_state.auth_status:
    st.title("🛡️ 系統授權驗證")
    with st.container():
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        t_input = st.text_input("請輸入您的 FinMind Token", type="password")
        if st.button("確認並開始監控", use_container_width=True):
            if t_input:
                with st.spinner("正在驗證 Token..."):
                    try:
                        # 測試抓取一筆資料來驗證 Token 是否有效
                        dl = DataLoader()
                        dl.login(token=t_input)
                        # 嘗試抓取隨便一個代碼的資訊，確保 Token 權限正常
                        test_data = dl.taiwan_stock_info()
                        if not test_data.empty:
                            st.session_state.api_token = t_input
                            st.session_state.auth_status = True
                            st.success("✅ 驗證成功！")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Token 有效但無法獲取資料，請檢查帳號權限。")
                    except Exception as e:
                        st.error(f"❌ 驗證失敗。錯誤原因：{str(e)}")
            else:
                st.warning("請輸入 Token 才能繼續。")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════
# 4. 主監控面板 (驗證通過後顯示)
# ══════════════════════════════════════════════════════════
st.title("⚡ 即時 AI 監控中...")

with st.sidebar:
    st.header("⚙️ 監控配置")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 1.5)
    st.divider()
    if st.button("🚪 登出/更換 Token"):
        st.session_state.auth_status = False
        st.rerun()

# 股票新增功能
with st.expander("➕ 新增監控標的"):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("股票代碼").strip()
    with c2:
        if st.button("加入"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                st.rerun()

# 資料抓取與渲染
dl = DataLoader()
dl.login(token=st.session_state.api_token)

# 預先抓取名稱對照表以加速顯示
@st.cache_data(ttl=3600)
def fetch_names(_api):
    df_info = _api.taiwan_stock_info()
    return dict(zip(df_info['stock_id'], df_info['stock_name']))

name_map = fetch_names(dl)

for code in st.session_state.watchlist:
    # 抓取最近 45 天日 K
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    try:
        df = dl.taiwan_stock_daily(stock_id=code, start_date=start_date)
        if not df.empty and len(df) > 20:
            c_name = name_map.get(code, f"個股 {code}")
            score, matches, last, prev = analyze_stock(df, m_list)
            chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
            
            color = "#ef4444" if chg > 0 else "#22c55e"
            tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
            alert =
