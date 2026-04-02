import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 數據抓取引擎 (FinMind + yfinance 備援)
# ══════════════════════════════════════════════════════════

def is_trading_time():
    """判斷台股交易時段"""
    now = datetime.now()
    if now.weekday() >= 5: return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=13, minute=35)

def get_smart_data(code, token):
    """盤中用 FinMind，盤後用 yfinance"""
    # 預設先嘗試 yfinance (非交易時段或 Token 節省)
    if not is_trading_time() or not token:
        yf_code = f"{code}.TW" if len(code) == 4 else f"{code}.TWO"
        try:
            df = yf.Ticker(yf_code).history(period="1mo")
            if not df.empty:
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                return df.rename(columns={'high': 'max', 'low': 'min', 'volume': 'volume'}), "Yahoo"
        except: pass

    # 交易時段則使用 FinMind
    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
    headers = {"Authorization": f"Bearer {token}"}
    params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        df = pd.DataFrame(res.json().get("data", []))
        if not df.empty:
            df = df.rename(columns={'Trading_Volume': 'volume'})
            return df, "FinMind"
    except: pass
    return pd.DataFrame(), "Error"

# ══════════════════════════════════════════════════════════
# 2. AI 分析邏輯 (補足五個指標)
# ══════════════════════════════════════════════════════════

def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20:
        return 50, [], "資料讀取中", "需要更多天數進行計算", "觀望", False

    df['close'] = pd.to_numeric(df['close'])
    df['max'] = pd.to_numeric(df['max'])
    df['min'] = pd.to_numeric(df['min'])
    df['volume'] = pd.to_numeric(df['volume'])

    matches = []
    
    # 1. RSI
    diff = df['close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.0001))))
    
    # 2. KD
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    rsv = 100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    
    # 3. MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    
    # 4. 布林通道 (Bollinger Bands)
    df['MA20'] = df['close'].rolling(20).mean()
    df['std'] = df['close'].rolling(20).std()
    df['Up'] = df['MA20'] + (df['std'] * 2)
    
    # 5. 成交量 (Volume)
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    
    # 指標判定
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI轉強")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.5: matches.append("📊 量能爆發")

    # 漲跌預警判斷
    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p

    # AI 決策
    status, reason, strategy = "中性觀察", "目前訊號尚未齊全，建議分批觀察。", "觀望"
    if len(matches) >= 3 and chg > 0:
        status, reason, strategy = "五指標多頭共振", "多項技術指標同步轉強且量能配合，趨勢極強。", "強力續抱"
    elif last['close'] < last['MA20'] and prev['close'] >= last['MA20']:
        status, reason, strategy = "破位訊號", "股價跌破月線支撐，短線轉弱，注意風險。", "減碼/清倉"

    score = 50 + (len(matches) * 10) if chg >= 0 else 40
    return int(score), matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# 3. Streamlit UI
# ══════════════════════════════════════════════════════════

st.set_page_config(page_title="AI 股市五星監控", layout="centered")

if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
if "tk" not in st.session_state: st.session_state.tk = ""

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; position: relative; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; display:inline-block; margin-top:5px; border:1px solid #334155; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:10px 0; border:1px solid #1e293b; }
    .warn-label { background:#facc15; color:#000; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold; position:absolute; top:10px; right:80px; }
</style>
""", unsafe_allow_html=True)

if not st.session_state.tk:
    st.title("🛡️ 權限驗證")
    tk = st.text_input("輸入 Token", type="password")
    if st.button("登入"): st.session_state.tk = tk; st.rerun()
    st.stop()

st.title("⚡ AI 自動監控面板")

with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("即時預警門檻 (%)", 0.5, 10.0, 1.5)
    new_code = st.text_input("新增代碼")
    if st.button("➕"): st.session_state.watchlist.append(new_code); st.rerun()
    if st.button("🚪 登出"): st.session_state.tk = ""; st.rerun()

for code in list(st.session_state.watchlist):
    df, source = get_smart_data(code, st.session_state.tk)
    if df.empty: continue

    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    warn_html = f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>' if is_warn else ""
    tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])

    st.markdown(f"""
    <div class="card" style="border-left-color: {color}">
        {warn_html}
        <div style="float:right; text-align:right;">
            <div style="color:{color}; font-size:1.3rem; font-weight:bold; border:2px solid {color}; border-radius:50%; width:45px; height:45px; display:flex; align-items:center; justify-content:center; margin-left:auto;">{score}</div>
            <div style="margin-top:8px; font-weight:bold; color:#38bdf8; font-size:0.85rem;">{strategy}</div>
        </div>
        <div style="font-size:1rem; font-weight:bold;">個股監控 ({code}) <span style="font-size:0.7rem; color:#475569;">來源:{source}</span></div>
        <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">{last_p:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
        <div class="dec-box">
            <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">AI 決策：{status}</div>
            <div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">{reason}</div>
        </div>
        <div>{tags_html if tags_html else '<span style="color:#475569; font-size:0.7rem;">掃描訊號中...</span>'}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code); st.rerun()

st.divider()
if is_trading_time():
    st.caption("🟢 盤中更新中...")
    time.sleep(60); st.rerun()
else:
    st.caption("🔴 非交易時段 (Yahoo 模式)")
    if st.button("🔄 手動刷新"): st.rerun()
