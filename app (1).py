import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心 API 抓取
# ══════════════════════════════════════════════════════════
def fetch_finmind(dataset, data_id, token, start_date=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": dataset}
    if data_id: params["data_id"] = data_id
    if start_date: params["start_date"] = start_date
    
    headers = {"Authorization": "Bearer " + token}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            return pd.DataFrame(res.json().get("data", []))
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 判斷是否為交易時段 (台股週一至週五 09:00 - 13:35)
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    start = now.replace(hour=9, minute=0, second=0)
    end = now.replace(hour=13, minute=35, second=0)
    return start <= now <= end

# ══════════════════════════════════════════════════════════
# 2. AI 技術分析邏輯
# ══════════════════════════════════════════════════════════
def analyze_logic(df, m_list):
    if df.empty or len(df) < 20: 
        return 50, [], "資料不足", "需至少20日數據進行分析", "觀望"
    
    df = df.copy()
    df['Close'] = pd.to_numeric(df['close'])
    df['High'] = pd.to_numeric(df['max'])
    df['Low'] = pd.to_numeric(df['min'])
    
    # RSI
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.0001))))
    
    # KD
    l9, h9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - l9) / (h9 - l9 + 0.0001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    
    # MACD OSC
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    df['OSC'] = macd - macd.ewm(span=9, adjust=False).mean()
    
    # 布林
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['Close'].rolling(20).std() * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "布林通道" in m_list and last['Close'] > last['Up']: matches.append("🌌 突破布林上軌")

    status, reason, strategy = "中性觀察", "指標處於整理區，建議等待趨勢明確。", "觀望"
    
    if len(matches) >= 2 and last['Close'] >= prev['Close']:
        status, reason, strategy = "多頭共振", "多項指標轉強且量能配合，趨勢向上。", "強力續抱"
    elif last['Close'] < last['MA20'] and prev['Close'] >= last['MA20']:
        status, reason, strategy = "支撐跌破", "跌破 20 日關鍵支撐線，趨勢轉弱。", "果斷清倉"
    
    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 40
    return int(score), matches, status, reason, strategy

# ══════════════════════════════════════════════════════════
# 3. 主 UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控", layout="centered")

# 初始化 Session State
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
if "tk" not in st.session_state:
    st.session_state.tk = ""

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border: 1px solid #1e2533; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.7rem; margin-right:5px; border:1px solid #334155; display:inline-block; margin-top:5px; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:12px 0; border:1px solid #1e293b; }
</style>
""", unsafe_allow_html=True)

if not st.session_state.tk:
    st.title("🛡️ 授權驗證")
    tk_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("啟動系統"):
        st.session_state.tk = tk_input
        st.rerun()
    st.stop()

st.title("⚡ AI 自動監控面板")

# 合併請求優化 (一次抓取全台股即時快照)
snapshot_df = fetch_finmind("TaiwanStockQuote", None, st.session_state.tk)

with st.sidebar:
    st.header("⚙️ 設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "布林通道"], default=["KD", "MACD"])
    new_code = st.text_input("新增代碼")
    if st.button("➕"):
        if new_code: st.session_state.watchlist.append(new_code.strip()); st.rerun()
    if st.button("🚪 登出"):
        st.session_state.tk = ""; st.rerun()

# 顯示監控清單
for code in list(st.session_state.watchlist):
    # 修正重點：使用 data_id 來對應快照資料
    if snapshot_df.empty:
        st.error("無法取得即時資料，請確認 Token 是否有效。")
        break

    target = snapshot_df[snapshot_df['data_id'] == code]
    if target.empty:
        st.info(f"🔍 暫無代碼 {code} 的即時數據")
        continue
    
    snap = target.iloc[0]
    
    # 抓取歷史數據做分析 (1 小時快取)
    @st.cache_data(ttl=3600)
    def get_analysis_data(c, t):
        sd = (datetime.now()-timedelta(days=45)).strftime('%Y-%m-%d')
        return fetch_finmind("TaiwanStockPrice", c, t, sd)
    
    hist_df = get_analysis_data(code, st.session_state.tk)
    score, matches, status, reason, strategy = analyze_logic(hist_df, m_list)
    
    chg = float(snap.get('change_rate', 0))
    color = "#ef4444" if chg >= 0 else "#22c55e"
    strat_color = "#38bdf8"
    if "強力" in strategy: strat_color = "#f87171"
    elif "清倉" in strategy: strat_color = "#4ade80"

    # HTML 渲染
    tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
    
    st.markdown(f"""
    <div class="card" style="border-left-color: {color}">
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.3rem; font-weight:bold; border:2px solid {color}; border-radius:50%; width:45px; height:45px; display:flex; align-items:center; justify-content:center; margin-left:auto;">{score}</div>
            <div style="margin-top:8px; font-weight:bold; color:{strat_color}; font-size:0.85rem;">{strategy}</div>
        </div>
        <div style="font-size:1rem; font-weight:bold;">{snap.get('stock_name', '股票')} ({code})</div>
        <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">{float(snap['last']):.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
        <div class="dec-box">
            <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">AI 決策：{status}</div>
            <div style="color:#f1f5f9; font-size:0.9rem; line-height:1.5;">{reason}</div>
        </div>
        <div>{tags_html if tags_html else '<span style="color:#475569; font-size:0.7rem;">監控中...</span>'}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code)
        st.rerun()

# ══════════════════════════════════════════════════════════
# 4. 自動刷新邏輯
# ══════════════════════════════════════════════════════════
st.divider()
if is_trading_time():
    st.caption("🟢 交易時段：每 60 秒自動同步行情")
    time.sleep(60)
    st.rerun()
else:
    st.caption("🔴 非交易時段：已暫停 API 請求以節省 Token。")
    if st.button("🔄 手動更新"): st.rerun()
