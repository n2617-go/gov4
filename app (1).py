import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心 API 封裝 (支援快照與歷史數據)
# ══════════════════════════════════════════════════════════
def fetch_finmind(dataset, data_id, token, start_date=None):
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": dataset}
    if data_id: params["data_id"] = data_id
    if start_date: params["start_date"] = start_date
    
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        data = res.json().get("data", [])
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

# 判斷是否為交易時段 (週一至週五 09:00 - 13:35)
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False # 週六日
    start = now.replace(hour=9, minute=0, second=0)
    end = now.replace(hour=13, minute=35, second=0)
    return start <= now <= end

# ══════════════════════════════════════════════════════════
# 2. AI 技術分析邏輯
# ══════════════════════════════════════════════════════════
def analyze_logic(df, m_list):
    if len(df) < 20: return 50, [], "資料不足", "需20日數據", "觀望"
    
    df['Close'] = pd.to_numeric(df['close'])
    df['High'] = pd.to_numeric(df['max'])
    df['Low'] = pd.to_numeric(df['min'])
    
    # RSI
    diff = df['Close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff>0,0).rolling(14).mean() / (-diff.where(diff<0,0).rolling(14).mean() + 0.0001))))
    # KD
    l9, h9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - l9) / (h9 - l9 + 0.0001))
    df['K'] = rsv.ewm(com=2).mean()
    # MACD 柱狀
    osc = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['OSC'] = osc - osc.ewm(span=9).mean()
    # 布林
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['Close'].rolling(20).std() * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "布林通道" in m_list and last['Close'] > last['Up']: matches.append("🌌 突破布林上軌")

    status, reason, strategy = "中性觀察", "指標不明確，建議觀望。", "觀望"
    if len(matches) >= 2: status, reason, strategy = "多頭共振", "多指標轉強，趨勢向上。", "強力續抱"
    elif last['Close'] < last['MA20'] and prev['Close'] >= last['MA20']: status, reason, strategy = "趨勢轉空", "跌破月線支撐，轉為弱勢。", "果斷清倉"
    
    score = 50 + (len(matches)*10) if last['Close'] >= prev['Close'] else 40
    return int(score), matches, status, reason, strategy

# ══════════════════════════════════════════════════════════
# 3. UI 介面與合併更新邏輯
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股海領航員", layout="centered")

# CSS 樣式 (穩定版)
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:15px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:12px; border:1px solid #1e2533; }
    .tag { background:#1e293b; color:#38bdf8; padding:2px 8px; border-radius:4px; font-size:0.7rem; margin-right:5px; border:1px solid #334155; }
    .dec-box { background:#0f172a; padding:10px; border-radius:8px; margin:10px 0; border:1px solid #1e293b; }
</style>
""", unsafe_allow_html=True)

if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "2603"]
if "tk" not in st.session_state: st.session_state.tk = ""

# 登入驗證
if not st.session_state.tk:
    tk = st.text_input("輸入 FinMind Token", type="password")
    if st.button("啟動系統"): st.session_state.tk = tk; st.rerun()
    st.stop()

st.title("📈 智慧監控面板")

# --- 合併請求優化區 ---
# 1. 抓取全台股即時快照 (只需 1 次 Request)
with st.spinner("同步全市場行情中..."):
    snapshot_df = fetch_finmind("TaiwanStockQuote", None, st.session_state.tk)

# 2. 側邊欄設定
with st.sidebar:
    st.write(f"📊 目前監控: {len(st.session_state.watchlist)} 檔")
    m_list = st.multiselect("指標", ["KD", "MACD", "布林通道"], default=["KD", "MACD"])
    add_code = st.text_input("新增代碼")
    if st.button("添加"): st.session_state.watchlist.append(add_code); st.rerun()
    if st.button("登出"): st.session_state.tk = ""; st.rerun()

# 3. 渲染清單
for code in st.session_state.watchlist:
    # 從快照中提取該股資料 (不耗 Token)
    stock_snap = snapshot_df[snapshot_df['stock_id'] == code]
    if stock_snap.empty: continue
    
    snap = stock_snap.iloc[0]
    
    # 抓取歷史數據做 AI 分析 (快取處理)
    @st.cache_data(ttl=3600)
    def get_hist(c, t):
        return fetch_finmind("TaiwanStockPrice", c, t, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
    
    hist_df = get_hist(code, st.session_state.tk)
    score, matches, status, reason, strategy = analyze_logic(hist_df, m_list)
    
    # 漲跌判斷
    chg = float(snap.get('change_rate', 0))
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # HTML 顯示
    tags = "".join([f'<span class="tag">{m}</span>' for m in matches])
    st.markdown(f"""
    <div class="card" style="border-left-color: {color}">
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.2rem; font-weight:bold;">{score} 分</div>
            <div style="color:#38bdf8; font-size:0.8rem; font-weight:bold;">{strategy}</div>
        </div>
        <div style="font-size:1rem; font-weight:bold;">{snap.get('stock_name', '股票')} ({code})</div>
        <div style="font-size:1.6rem; font-weight:900; color:{color};">{float(snap['last']):.2f} <span style="font-size:0.9rem;">({chg:+.2f}%)</span></div>
        <div class="dec-box">
            <div style="color:#94a3b8; font-size:0.7rem;">AI 決策：{status}</div>
            <div style="color:#f1f5f9; font-size:0.85rem;">{reason}</div>
        </div>
        {tags if tags else '<span style="color:#475569; font-size:0.7rem;">監控中...</span>'}
    </div>
    """, unsafe_allow_html=True)
    
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code); st.rerun()

# ══════════════════════════════════════════════════════════
# 4. 自動刷新邏輯 (省錢關鍵)
# ══════════════════════════════════════════════════════════
st.divider()
if is_trading_time():
    st.caption("🟢 交易時段：每 60 秒自動更新行情")
    time.sleep(60)
    st.rerun()
else:
    st.caption("🔴 非交易時段：系統暫停 API 請求以節省 Token。")
    if st.button("手動刷新"): st.rerun()
