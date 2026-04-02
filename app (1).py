import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心工具函式
# ══════════════════════════════════════════════════════════

def is_trading_time():
    """判斷現在是否為台股交易時段 (週一至五 09:00 - 13:35)"""
    now = datetime.now()
    if now.weekday() >= 5: return False
    start = now.replace(hour=9, minute=0, second=0)
    end = now.replace(hour=13, minute=35, second=0)
    return start <= now <= end

def fetch_finmind_snapshot(token):
    """合併請求：一次抓取全市場即時快照"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockQuote"}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        return pd.DataFrame(res.json().get("data", []))
    except:
        return pd.DataFrame()

def get_hist_data(code, token):
    """智慧切換：盤中用 FinMind 歷史 API，盤後用 yfinance"""
    if is_trading_time() and token:
        # 盤中：使用 FinMind 獲取精確日線
        url = "https://api.finmindtrade.com/api/v4/data"
        start_date = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
        params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            df = pd.DataFrame(res.json().get("data", []))
            if not df.empty:
                df = df.rename(columns={'max': 'high', 'min': 'low', 'Trading_Volume': 'volume'})
                return df
        except: pass

    # 盤後 或 FinMind 失敗：使用 yfinance (免費備援)
    yf_code = f"{code}.TW" if len(code) == 4 else f"{code}.TWO"
    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period="1mo")
        if df.empty: return pd.DataFrame()
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'})
        return df
    except:
        return pd.DataFrame()

# ══════════════════════════════════════════════════════════
# 2. AI 分析邏輯
# ══════════════════════════════════════════════════════════

def run_ai_analysis(df, m_list):
    if df.empty or len(df) < 20:
        return 50, [], "資料計算中", "請稍候...", "觀望"
    
    df['close'] = pd.to_numeric(df['close'])
    # 計算 RSI
    diff = df['close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff > 0, 0).rolling(14).mean() / (-diff.where(diff < 0, 0).rolling(14).mean() + 0.0001))))
    # 計算 KD
    l9, h9 = df['low'].rolling(9).min(), df['high'].rolling(9).max()
    rsv = 100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    # 計算 MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 30 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢突破")

    status, reason, strategy = "趨勢觀察", "指標目前尚無明顯方向。", "觀望"
    if len(matches) >= 2: status, reason, strategy = "多頭共振", "多項指標同時翻紅，能量強勁。", "強力續抱"
    elif last['close'] < df['close'].rolling(20).mean().iloc[-1]: status, reason, strategy = "偏弱整理", "跌破月線支撐，建議轉向防禦。", "減碼/清倉"

    score = 50 + (len(matches) * 15) if last['close'] >= prev['close'] else 40
    return int(score), matches, status, reason, strategy

# ══════════════════════════════════════════════════════════
# 3. Streamlit UI 頁面
# ══════════════════════════════════════════════════════════

st.set_page_config(page_title="AI 雙引擎監控", layout="centered")

# 初始化
if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
if "tk" not in st.session_state: st.session_state.tk = ""

# 自定義 CSS
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; display:inline-block; margin-top:5px; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:10px 0; border:1px solid #1e293b; }
</style>
""", unsafe_allow_html=True)

if not st.session_state.tk:
    st.title("🛡️ 專業版授權驗證")
    tk_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("啟動系統"): st.session_state.tk = tk_input; st.rerun()
    st.stop()

st.title("⚡ AI 自動監控面板")

# 盤中合併抓取
snapshot_df = fetch_finmind_snapshot(st.session_state.tk) if is_trading_time() else pd.DataFrame()

with st.sidebar:
    st.header("⚙️ 控制台")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI"], default=["KD", "MACD", "RSI"])
    new_code = st.text_input("新增代碼")
    if st.button("➕"):
        if new_code: st.session_state.watchlist.append(new_code.strip()); st.rerun()
    if st.button("🚪 登出"): st.session_state.tk = ""; st.rerun()

# 渲染監控卡片
for code in list(st.session_state.watchlist):
    hist_df = get_hist_data(code, st.session_state.tk)
    if hist_df.empty: continue

    score, matches, status, reason, strategy = run_ai_analysis(hist_df, m_list)
    last_price = hist_df.iloc[-1]['close']
    prev_price = hist_df.iloc[-2]['close']
    chg = (last_price - prev_price) / prev_price * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])

    # 顯示卡片 (穩定版 HTML)
    st.markdown(f"""
    <div class="card" style="border-left-color: {color}">
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.3rem; font-weight:bold; border:2px solid {color}; border-radius:50%; width:45px; height:45px; display:flex; align-items:center; justify-content:center; margin-left:auto;">{score}</div>
            <div style="margin-top:8px; font-weight:bold; color:#38bdf8; font-size:0.85rem;">{strategy}</div>
        </div>
        <div style="font-size:1rem; font-weight:bold;">個股監控 ({code})</div>
        <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">{last_price:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
        <div class="dec-box">
            <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">AI 決策：{status}</div>
            <div style="color:#f1f5f9; font-size:0.9rem; line-height:1.5;">{reason}</div>
        </div>
        <div>{tags_html if tags_html else '<span style="color:#475569; font-size:0.7rem;">監控中...</span>'}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(f"🗑️ {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code); st.rerun()

# 自動刷新
st.divider()
if is_trading_time():
    st.caption("🟢 盤中監控：每 60 秒同步 FinMind 資料")
    time.sleep(60); st.rerun()
else:
    st.caption("🔴 非交易時段：使用 Yahoo 備援，不消耗 Token。")
    if st.button("🔄 手動重新整理"): st.rerun()
