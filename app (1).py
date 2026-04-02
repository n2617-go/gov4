
import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 初始化與 Cookies
# ══════════════════════════════════════════════════════════
controller = CookieController()
cookie_token = controller.get('finmind_token')

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 核心抓取引擎 (修正 NaN 與 中文名稱)
# ══════════════════════════════════════════════════════════
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=13, minute=35)

def get_smart_data(code, token):
    # 自動判斷上市 (.TW) 或 上櫃 (.TWO)
    # 簡單判斷：4碼通常是上市，5碼或以上(如權證、部分ETF)需視情況，這裡增加判斷邏輯
    is_otc = len(code) >= 5 or code.startswith('00') and int(code[:2]) >= 60 # 簡易邏輯
    yf_code = f"{code}.TW" if not is_otc else f"{code}.TWO"
    
    # 常用股票中文對照表 (當 API 抓不到名稱時的備援)
    name_map = {"2330": "台積電", "2317": "鴻海", "2603": "長榮", "2454": "聯發科"}
    
    # 優先嘗試 Yahoo (非交易時段或無 Token)
    if not is_trading_time() or not token:
        try:
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period="1mo")
            if not df.empty:
                # 取得名稱：優先從 info 抓，失敗就用對照表，再失敗就顯示代號
                info = ticker.info
                c_name = info.get('longName') or info.get('shortName') or name_map.get(code, f"個股 {code}")
                
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns] # 統一小寫
                return df.rename(columns={'high':'max', 'low':'min'}), "Yahoo", c_name
        except: pass

    # 交易時段用 FinMind
    if token:
        url = "https://api.finmindtrade.com/api/v4/data"
        start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
        headers = {"Authorization": "Bearer " + token}
        params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            result = res.json()
            if result.get("data"):
                df = pd.DataFrame(result["data"])
                # FinMind 通常會帶 stock_name 欄位
                c_name = df.iloc[-1].get('stock_name') or name_map.get(code, f"個股 {code}")
                return df.rename(columns={'Trading_Volume': 'volume'}), "FinMind", c_name
        except: pass
    
    return pd.DataFrame(), "Error", code

# ══════════════════════════════════════════════════════════
# 3. AI 分析邏輯
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20: return 50, [], "數據不足", "等待載入", "觀望", False
    
    # 關鍵：清理資料，確保沒有 NaN
    for col in ['close', 'max', 'min', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    matches = []
    # RSI
    diff = df['close'].diff()
    gain = diff.where(diff > 0, 0).rolling(14).mean()
    loss = -diff.where(diff < 0, 0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.0001))))
    # KD
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()
    # MACD
    ema12, ema26 = df['close'].ewm(span=12).mean(), df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    # 布林
    df['MA20'] = df['close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['close'].rolling(20).std() * 2)
    # 成交量
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI走強")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.5: matches.append("📊 量能爆發")

    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    
    status, strategy = "觀察中", "觀望"
    if len(matches) >= 3 and chg > 0: status, strategy = "多頭共振", "強力續抱"
    elif last['close'] < last['MA20']: status, strategy = "支撐跌破", "減碼"

    return int(50 + len(matches)*10), matches, status, "技術指標綜合分析。", strategy, is_warning

# ══════════════════════════════════════════════════════════
# 4. 主 UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控", layout="centered")

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; position: relative; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; display:inline-block; margin-top:5px; border:1px solid #334155; }
    .warn-label { background:#facc15; color:#000; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold; position:absolute; top:10px; right:80px; }
</style>
""", unsafe_allow_html=True)

if not st.session_state.get("tk"):
    st.title("🛡️ 專業監控登入")
    tk_input = st.text_input("輸入 Token", type="password")
    remember = st.checkbox("記住我的 Token (30天)")
    if st.button("啟動系統"):
        st.session_state.tk = tk_input
        if remember: controller.set('finmind_token', tk_input, max_age=2592000)
        st.rerun()
    st.stop()

st.title("⚡ AI 自動監控面板")

with st.sidebar:
    st.header("⚙️ 設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    
    st.divider()
    new_code = st.text_input("➕ 新增代碼")
    if st.button("確認新增"):
        if new_code: st.session_state.watchlist.append(new_code); st.rerun()
    
    if st.button("🚪 登出系統"):
        controller.remove('finmind_token')
        st.session_state.tk = ""
        st.rerun()

# 顯示監控
for code in list(st.session_state.watchlist):
    df, source, c_name = get_smart_data(code, st.session_state.tk)
    
    if df.empty:
        st.error(f"❌ {code} 資料抓取失敗，請確認代碼是否正確。")
        continue

    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # 構建 HTML
    card_html = f'<div class="card" style="border-left-color: {color}">'
    if is_warn: card_html += f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>'
    card_html += f'<div style="float:right; text-align:right;"><div style="color:{color}; font-size:1.4rem; font-weight:bold;">{score}</div><div style="color:#38bdf8; font-size:0.8rem;">{strategy}</div></div>'
    card_html += f'<div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) <span style="font-size:0.7rem; color:#475569;">[{source}]</span></div>'
    card_html += f'<div style="font-size:1.8rem; font-weight:900; color:{color}; margin:8px 0;">{last_p:.2f} <small style="font-size:1rem;">({chg:+.2f}%)</small></div>'
    
    tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
    card_html += f'<div>{tags_html if tags_html else "掃描中..."}</div></div>'
    
    st.markdown(card_html, unsafe_allow_html=True)
    
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code); st.rerun()

st.divider()
if is_trading_time():
    st.caption("🟢 盤中更新中 (每 60 秒)")
    time.sleep(60); st.rerun()
else:
    st.caption("🔴 非交易時段 (Yahoo 模式)")
    if st.button("🔄 手動刷新"): st.rerun()
