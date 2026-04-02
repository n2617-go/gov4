import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════
# 1. 核心 API 抓取
# ══════════════════════════════════════════════════════════
def fetch_finmind_api(dataset, data_id, token, days=90):
    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {"dataset": dataset, "start_date": start_date}
    if data_id:
        params["data_id"] = data_id

    headers = {
        "Authorization": "Bearer " + token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    }

    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        if res.status_code != 200:
            return pd.DataFrame(), f"HTTP {res.status_code}"
        
        result = res.json()
        if result.get("msg") == "success" and result.get("data"):
            return pd.DataFrame(result["data"]), "success"
        return pd.DataFrame(), result.get("msg", "Empty Data")
    except Exception as e:
        return pd.DataFrame(), str(e)

# ══════════════════════════════════════════════════════════
# 2. AI 技術分析邏輯
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list):
    df = df.copy()
    rename_map = {'close': 'Close', 'max': 'High', 'min': 'Low', 'open': 'Open', 'Trading_Volume': 'Volume'}
    df = df.rename(columns=rename_map)

    for col in ['Close', 'High', 'Low', 'Open']:
        if col not in df.columns: return 50, [], None, None, {}
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Volume' in df.columns:
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
    
    df = df.dropna(subset=['Close']).reset_index(drop=True)
    if len(df) < 20: return 50, [], df.iloc[-1], None, {"status":"資料不足", "reason":"需至少20日數據", "strategy":"觀望"}

    # --- 技術指標計算 ---
    # RSI
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.00001))))
    
    # KD
    low9 = df['Low'].rolling(9).min()
    high9 = df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low9) / (high9 - low9 + 0.00001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # MACD
    e12 = df['Close'].ewm(span=12, adjust=False).mean()
    e26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = e12 - e26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['OSC'] = df['MACD'] - df['Signal']
    
    # 布林通道
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Upper'] = df['MA20'] + (df['Close'].rolling(20).std() * 2)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    matches = []

    # 指標符合判定
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI突破50")
    if "布林通道" in m_list and last['Close'] > last['Upper']: matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and last.get('Volume', 0) > df['Volume'].tail(5).mean() * 1.5: matches.append("📊 量能爆發")

    # --- AI 決策邏輯 ---
    status, reason, strategy = "中性觀察", "目前指標訊號不明確，建議觀望等待趨勢。", "觀望"
    
    # 1. 強多 (五指標共振)
    if len(matches) >= 3 and last['Close'] >= prev['Close']:
        status, reason, strategy = "五指標共振 (強多)", "多項指標同步轉強且量能齊揚，趨勢極強，建議持股續抱。", "強力買進 / 續抱"
    # 2. 高檔噴發
    elif last['RSI'] > 75 and last['Close'] > last['Upper']:
        status, reason, strategy = "指標高檔鈍化", "股價沿布林上軌噴發，RSI過熱但趨勢未破，建議設移動停利。", "警戒續抱"
    # 3. 頂背離 (簡單判定：股價創10日高但MACD柱狀圖未創高)
    elif last['Close'] > df['Close'].shift(1).tail(10).max() and last['OSC'] < df['OSC'].shift(1).tail(10).max():
        status, reason, strategy = "背離訊號", "股價創高但 MACD 縮小，上方有壓，建議見好就收，分批落袋。", "分批賣出"
    # 4. 轉空
    elif last['Close'] < last['MA20'] and prev['Close'] >= prev['MA20']:
        status, reason, strategy = "跌破關鍵支撐", "帶量跌破布林中軌，KD高檔死叉，短線趨勢轉空，建議先出場觀望。", "果斷清倉"
    # 5. 底背離/打底
    elif last['RSI'] < 30 and last['K'] > prev['K']:
        status, reason, strategy = "低檔打底完成", "RSI底部背離且成交量緩步加溫，殺低後不再破底，建議小量試單。", "小量試單"

    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    decision = {"status": status, "reason": reason, "strategy": strategy}
    
    return int(score), matches, last, prev, decision

# ══════════════════════════════════════════════════════════
# 3. UI 樣式與系統邏輯
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股 AI 監控專業版", layout="centered")

_CSS = """
<style>
    html, body, [data-testid="stAppViewContainer"] { background-color: #0a0d14 !important; color: white; }
    .card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8; margin-bottom:15px; border: 1px solid #1e2533; }
    .tag { background: #0e2233; color: #38bdf8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 5px; border: 1px solid #1e4d6b; }
    .decision-box { background: #1e293b; padding: 12px; border-radius: 8px; margin: 12px 0; border: 1px solid #334155; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

if "auth" not in st.session_state: st.session_state.auth = False
if "tk" not in st.session_state: st.session_state.tk = ""
if "watchlist" not in st.session_state: st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

if not st.session_state.auth:
    st.title("🛡️ 專業版授權驗證")
    t_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("驗證並開啟 AI 監控", use_container_width=True):
        check_df, msg = fetch_finmind_api("TaiwanStockInfo", None, t_input)
        if not check_df.empty:
            st.session_state.tk, st.session_state.auth = t_input, True
            st.rerun()
        else: st.error("❌ 驗證失敗: " + msg)
    st.stop()

# ══════════════════════════════════════════════════════════
# 4. 主監控面板
# ══════════════════════════════════════════════════════════
st.title("⚡ AI 自動監控中")

with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    new_code = st.text_input("新增股票代碼")
    if st.button("➕ 加入監控"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            st.rerun()
    if st.button("🚪 登出系統"):
        st.session_state.auth = False
        st.rerun()

@st.cache_data(ttl=3600)
def get_name_map(token):
    df, _ = fetch_finmind_api("TaiwanStockInfo", None, token)
    return dict(zip(df['stock_id'], df['stock_name'])) if not df.empty else {}

name_map = get_name_map(st.session_state.tk)

for code in list(st.session_state.watchlist):
    df, msg = fetch_finmind_api("TaiwanStockPrice", code, st.session_state.tk)
    if not df.empty and len(df) >= 2:
        score, matches, last, prev, decision = analyze_stock(df, m_list)
        
        # 數值計算
        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
        color = "#ef4444" if chg >= 0 else "#22c55e"
        strat_color = "#38bdf8"
        if "買進" in decision['strategy']: strat_color = "#f87171"
        elif "賣出" in decision['strategy'] or "清倉" in decision['strategy']: strat_color = "#4ade80"

        # HTML 渲染
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        st.markdown(f"""
            <div class="card" style="border-left-color: {color}">
                <div style="float:right; text-align:right;">
                    <div style="font-size:22px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:45px; height:45px; display:flex; align-items:center; justify-content:center; margin-left:auto;">{score}</div>
                    <div style="margin-top:8px; font-weight:bold; color:{strat_color}; font-size:0.9rem;">{decision['strategy']}</div>
                </div>
                <div style="font-size:1rem; font-weight:bold;">{name_map.get(code, code)} ({code}) <span style="font-size:0.7rem; color:#94a3b8;">[{str(last['date'])[:10]}]</span></div>
                <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">{last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span></div>
                
                <div class="decision-box">
                    <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">AI 決策說明：{decision['status']}</div>
                    <div style="color:#f8fafc; font-size:0.9rem; line-height:1.5;">{decision['reason']}</div>
                </div>
                
                <div>{tags_html if tags_html else '<span style="color:#64748b; font-size:0.8rem;">指標整理中...</span>'}</div>
            </div>
        """, unsafe_allow_html=True)

        if st.button("🗑️ 移除 " + code, key="del_" + code):
            st.session_state.watchlist.remove(code)
            st.rerun()
    else:
        st.warning(f"⚠️ {code}: 抓取失敗 ({msg})")

# ══════════════════════════════════════════════════════════
# 5. 自動刷新
# ══════════════════════════════════════════════════════════
st.divider()
placeholder = st.empty()
for remaining in range(60, 0, -1):
    placeholder.caption(f"⏱️ 下次自動刷新倒數：{remaining} 秒")
    time.sleep(1)
st.rerun()
