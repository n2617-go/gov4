import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 初始化與 Cookies 處理
# ══════════════════════════════════════════════════════════
controller = CookieController()
cookie_token = controller.get('finmind_token')

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 數據抓取邏輯 (強化中文名稱與代碼判斷)
# ══════════════════════════════════════════════════════════
def get_smart_data(code, token):
    # 台灣股市代碼判斷
    yf_code = code + ".TW" if len(code) <= 4 else code + ".TWO"
    
    # 常用中文名稱對照 (備援方案)
    name_map = {"2330": "台積電", "2317": "鴻海", "2603": "長榮", "2454": "聯發科", "0050": "元大台灣50"}
    
    # 優先嘗試 Yahoo (非交易時段或無 Token)
    try:
        ticker = yf.Ticker(yf_code)
        # 增加抓取天數到 3 個月，確保指標計算不會因為數據不足而顯示「掃描中」
        df = ticker.history(period="3mo") 
        if not df.empty:
            info = ticker.info
            # 優先抓取 Yahoo 內建名稱，若無則查表
            c_name = info.get('longName') or info.get('shortName') or name_map.get(code, "個股 " + code)
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            return df.rename(columns={'high':'max', 'low':'min'}), "Yahoo", c_name
    except: pass

    # 交易時段備援 FinMind (如果有 Token)
    if token:
        url = "https://api.finmindtrade.com/api/v4/data"
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        headers = {"Authorization": "Bearer " + token}
        params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            data = res.json().get("data", [])
            if data:
                df = pd.DataFrame(data)
                c_name = data[-1].get('stock_name') or name_map.get(code, "個股 " + code)
                return df.rename(columns={'Trading_Volume': 'volume'}), "FinMind", c_name
        except: pass
    
    return pd.DataFrame(), "Error", code

# ══════════════════════════════════════════════════════════
# 3. AI 分析邏輯 (解決掃描中與決策說明缺失)
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list, warn_p):
    # 確保資料量足夠計算 20 日均線
    if df.empty or len(df) < 20: 
        return 50, [], "初始化中", "數據累積中，請稍候...", "觀望", False
    
    # 清理資料
    for col in ['close', 'max', 'min', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    matches = []
    # 指標計算
    # 1. RSI
    diff = df['close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff > 0, 0).rolling(14).mean() / (-diff.where(diff < 0, 0).rolling(14).mean() + 0.0001))))
    # 2. KD
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()
    # 3. MACD
    ema12, ema26 = df['close'].ewm(span=12).mean(), df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    # 4. 布林
    df['MA20'] = df['close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['close'].rolling(20).std() * 2)
    # 5. 成交量
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    
    # 判定符合指標
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI強勢")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.3: matches.append("📊 量能爆發")

    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    
    # --- AI 決策邏輯優化 ---
    status, strategy = "中性觀察", "觀望"
    reason = "目前多空訊號不明，建議等待量價突破月線支撐。"
    
    if len(matches) >= 3 and chg > 0:
        status, strategy = "多頭共振", "強力續抱"
        reason = f"目前符合 {len(matches)} 項多頭指標，且股價處於上升軌道，動能極強。"
    elif last['close'] < last['MA20']:
        status, strategy = "空頭警訊", "減碼/清倉"
        reason = "股價已跌破 20 日月線支撐，且技術指標轉弱，建議縮減部位規避風險。"
    elif len(matches) >= 1:
        status, strategy = "反彈嘗試", "少量試單"
        reason = "部分指標出現轉強訊號，但尚未形成整體趨勢，適合小量分批佈局。"

    score = int(50 + (len(matches) * 10) if chg >= 0 else 40)
    return score, matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# 4. 主 UI 介面
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控 (穩定版)", layout="centered")

# CSS 樣式
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card { background:#111827; padding:18px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border:1px solid #1e2533; position: relative; }
    .tag { background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:0.75rem; margin-right:5px; display:inline-block; margin-top:5px; border:1px solid #334155; }
    .dec-box { background:#0f172a; padding:12px; border-radius:8px; margin:12px 0; border:1px solid #1e293b; }
    .warn-label { background:#facc15; color:#000; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold; position:absolute; top:10px; right:80px; }
</style>
""", unsafe_allow_html=True)

# 登入邏輯
if not st.session_state.get("tk"):
    st.title("🛡️ 專業股市監控")
    tk_input = st.text_input("輸入 Token", type="password")
    if st.button("登入"):
        st.session_state.tk = tk_input
        controller.set('finmind_token', tk_input, max_age=2592000)
        st.rerun()
    st.stop()

# 側邊欄 (定義 m_list 與 warn_p，解決 NameError)
with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    st.divider()
    new_code = st.text_input("➕ 新增股票代碼")
    if st.button("確認新增"):
        if new_code: st.session_state.watchlist.append(new_code); st.rerun()
    if st.button("🚪 登出系統"):
        controller.remove('finmind_token'); st.session_state.tk = ""; st.rerun()

# 渲染列表
st.title("⚡ AI 自動監控面板")
for code in list(st.session_state.watchlist):
    df, source, c_name = get_smart_data(code, st.session_state.tk)
    if df.empty: continue

    # 在這裡呼叫分析，確保 m_list 和 warn_p 已定義
    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # 顯示 HTML 卡片
    html_card = f'<div class="card" style="border-left-color: {color}">'
    if is_warn: html_card += f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>'
    html_card += f'<div style="float:right; text-align:right;"><div style="color:{color}; font-size:1.4rem; font-weight:bold;">{score}</div><div style="color:#38bdf8; font-size:0.85rem; font-weight:bold;">{strategy}</div></div>'
    html_card += f'<div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code}) <span style="font-size:0.7rem; color:#475569;">[{source}]</span></div>'
    html_card += f'<div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">{last_p:.2f} <small style="font-size:1rem;">({chg:+.2f}%)</small></div>'
    
    # AI 決策說明區塊 (修正顯示問題)
    html_card += f'<div class="dec-box"><div style="color:#94a3b8; font-size:0.75rem; font-weight:bold;">AI 決策：{status}</div><div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">{reason}</div></div>'
    
    tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
    html_card += f'<div>{tags_html if tags_html else "掃描訊號中..."}</div></div>'
    
    st.markdown(html_card, unsafe_allow_html=True)
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code); st.rerun()
