import streamlit as st
import pandas as pd
import numpy as np
import time
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 核心資料與分析引擎
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list):
    """計算技術指標並判定符合項"""
    df = df.copy()
    # 轉換欄位名稱
    df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
    
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
    df['Upper'] = ma20 + (df['Close'].rolling(20).std() * 2)

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
# 2. UI 樣式設定
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控 (授權版)", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border-top: 1px solid rgba(255,255,255,0.05); }
    .tag { background: rgba(56, 189, 248, 0.12); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
    .auth-box { background: #1e293b; padding: 30px; border-radius: 15px; text-align: center; border: 1px solid #334155; }
</style>
""", unsafe_allow_html=True)

# 初始化 Session
if "auth" not in st.session_state: st.session_state.auth = False
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "00631L", "2454", "2603"]

# ══════════════════════════════════════════════════════════
# 3. 登入介面 (第一層門檻)
# ══════════════════════════════════════════════════════════
if not st.session_state.auth:
    st.title("🛡️ 台股 AI 監控系統")
    st.markdown("請先輸入您的 FinMind Token 以解鎖即時監控功能。")
    
    with st.container():
        st.markdown('<div class="auth-box">', unsafe_allow_html=True)
        token_input = st.text_input("FinMind Token", type="password", placeholder="請貼上您的 API Token")
        if st.button("確認輸入並開始掃描", use_container_width=True):
            if token_input:
                try:
                    # 測試登入
                    test_api = DataLoader()
                    test_api.login(token=token_input)
                    st.session_state.api_token = token_input
                    st.session_state.auth = True
                    st.success("✅ 驗證成功！正在啟動監控引擎...")
                    time.sleep(1)
                    st.rerun()
                except:
                    st.error("❌ Token 驗證失敗，請確認是否輸入正確。")
            else:
                st.warning("⚠️ 請輸入 Token 才能繼續。")
        st.markdown('</div>', unsafe_allow_html=True)
        st.info("💡 提示：您可以前往 FinMind 官網免費申請 API Token。")
    st.stop() # 停止執行後續程式碼

# ══════════════════════════════════════════════════════════
# 4. 主監控介面 (驗證後顯示)
# ══════════════════════════════════════════════════════════
st.title("⚡ 即時監控中...")

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 監控參數")
    m_list = st.multiselect("啟用分析指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 1.5)
    st.divider()
    if st.button("🚪 登出並更換 Token"):
        st.session_state.auth = False
        st.rerun()

# 新增股票
with st.expander("➕ 新增關注標的", expanded=False):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("股票代碼 (例: 2603)").strip()
    with c2:
        if st.button("加入監控"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                st.rerun()

# 數據引擎載入
api = DataLoader()
api.login(token=st.session_state.api_token)

# 獲取全台股名稱清單 (用於中文顯示)
@st.cache_data(ttl=3600)
def get_name_map():
    df_info = api.taiwan_stock_info()
    return dict(zip(df_info['stock_id'], df_info['stock_name']))

name_map = get_name_map()

# 掃描渲染
for code in st.session_state.watchlist:
    # 抓取最近 45 天數據
    start_dt = (pd.Timestamp.now() - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    df = api.taiwan_stock_daily(stock_id=code, start_date=start_dt)
    
    if not df.empty:
        c_name = name_map.get(code, f"個股 {code}")
        score, matches, last, prev = analyze_stock(df, m_list)
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        
        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        alert = f"<span style='color:#facc15;'>🚨 預警({warn_p}%)</span>" if abs(chg) >= warn_p else ""

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) {alert}</div>
            <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">
                {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
            </div>
            <div style="margin-top:5px;"><b>符合指標：</b><br>{tags_html if tags_html else "掃描中..."}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            st.rerun()
    else:
        st.error(f"❌ {code} 資料獲取失敗")

# 自動刷新 (60秒)
time.sleep(60)
st.rerun()
