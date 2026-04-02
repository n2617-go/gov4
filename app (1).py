import streamlit as st
import pandas as pd
import numpy as np
import time
from FinMind.data import DataLoader

# ══════════════════════════════════════════════════════════
# 1. 技術指標分析邏輯
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list):
    df = df.copy()
    # 欄位標準化
    df = df.rename(columns={'close':'Close', 'max':'High', 'min':'Low', 'Revenue':'Volume', 'open':'Open'})
    
    # 避免數據不足報錯
    if len(df) < 20:
        return 50, [], df.iloc[-1], df.iloc[-2]

    # RSI (14)
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.00001))))
    
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
    
    # 指標符合判定
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and last['Volume'] > df['Volume'].tail(5).mean() * 1.5: matches.append("📊 量能爆發")
    
    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    return int(score), matches, last, prev

# ══════════════════════════════════════════════════════════
# 2. UI 樣式設定
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 監控系統", layout="centered")

st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border: 1px solid rgba(255,255,255,0.05); }
    .tag { background: rgba(56, 189, 248, 0.12); color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid rgba(56, 189, 248, 0.3); }
    .auth-container { background: #1e293b; padding: 40px; border-radius: 15px; border: 1px solid #334155; margin-top: 50px; text-align: center; }
</style>
""", unsafe_allow_html=True)

if "auth_ok" not in st.session_state: st.session_state.auth_ok = False
if "my_token" not in st.session_state: st.session_state.my_token = ""
if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "00631L", "2454", "2603"]

# ══════════════════════════════════════════════════════════
# 3. 登入門檻 (驗證 Token)
# ══════════════════════════════════════════════════════════
if not st.session_state.auth_ok:
    st.title("🛡️ 系統授權驗證")
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    t_input = st.text_input("請輸入 FinMind Token", type="password", placeholder="在此貼上您的 Token")
    if st.button("確認輸入並開始監控", use_container_width=True):
        if t_input:
            with st.spinner("驗證中..."):
                try:
                    dl = DataLoader()
                    dl.login(token=t_input)
                    # 測試抓取確保 Token 有效
                    test = dl.taiwan_stock_info()
                    if not test.empty:
                        st.session_state.my_token = t_input
                        st.session_state.auth_ok = True
                        st.success("✅ 驗證成功！")
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 驗證失敗：{str(e)}")
        else:
            st.warning("請輸入 Token 才能繼續。")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════
# 4. 主監控面板
# ══════════════════════════════════════════════════════════
st.title("⚡ 台股 AI 即時監控")

with st.sidebar:
    st.header("⚙️ 監控參數")
    m_list = st.multiselect("啟用分析指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 5.0, 1.5)
    st.divider()
    if st.button("🚪 登出並更換 Token"):
        st.session_state.auth_ok = False
        st.rerun()

# 股票新增
with st.expander("➕ 新增關注股票"):
    c1, c2 = st.columns([3, 1])
    with c1:
        new_id = st.text_input("輸入股票代碼").strip()
    with c2:
        if st.button("加入"):
            if new_id and new_id not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_id)
                st.rerun()

# 資料引擎載入
api = DataLoader()
api.login(token=st.session_state.my_token)

# 名稱對應表快取
@st.cache_data(ttl=3600)
def fetch_name_dict(_token):
    temp_api = DataLoader()
    temp_api.login(token=_token)
    df_info = temp_api.taiwan_stock_info()
    return dict(zip(df_info['stock_id'], df_info['stock_name']))

name_map = fetch_name_dict(st.session_state.my_token)

# 渲染卡片
for code in st.session_state.watchlist:
    start_dt = (pd.Timestamp.now() - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    try:
        df = api.taiwan_stock_daily(stock_id=code, start_date=start_dt)
        if not df.empty and len(df) > 10:
            c_name = name_map.get(code, f"個股 {code}")
            score, matches, last, prev = analyze_stock(df, m_list)
            chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
            
            color = "#ef4444" if chg > 0 else "#22c55e"
            tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
            alert_text = f"<span style='color:#facc15;'>🚨 預警({warn_p}%)</span>" if abs(chg) >= warn_p else ""

            st.markdown(f"""
            <div class="card" style="border-left-color: {color}">
                <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
                <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) {alert_text}</div>
                <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">
                    {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
                </div>
                <div><b>符合指標：</b><br>{tags_html if tags_html else "掃描中..."}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
                st.session_state.watchlist.remove(code)
                st.rerun()
        else:
            st.warning(f"⚠️ {code} 資料獲取失敗")
    except Exception as e:
        st.error(f"❌ 錯誤: {code}")

time.sleep(60)
st.rerun()
