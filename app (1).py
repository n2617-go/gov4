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

    params = {
        "dataset": dataset,
        "token": token,
        "start_date": start_date
    }

    # 只有指定股票代碼時才加入 data_id
    if data_id:
        params["data_id"] = data_id

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    }

    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)

        if res.status_code != 200:
            # 嘗試取得 API 回傳的錯誤訊息
            try:
                err_msg = res.json().get("msg", f"HTTP {res.status_code}")
            except Exception:
                err_msg = f"HTTP {res.status_code}"
            return pd.DataFrame(), err_msg

        result = res.json()
        if result.get("msg") == "success" and result.get("data"):
            df = pd.DataFrame(result["data"])
            return df, "success"
        else:
            return pd.DataFrame(), result.get("msg", "Empty Data")
    except Exception as e:
        return pd.DataFrame(), str(e)


def analyze_stock(df, m_list):
    """計算技術指標與 AI 分數"""
    df = df.copy()

    # ✅ 修正：TaiwanStockDaily 實際欄位名稱
    # 原始欄位：date, stock_id, Trading_Volume, Trading_money, open, max, min, close, spread, Trading_turnover
    rename_map = {
        'close': 'Close',
        'max': 'High',
        'min': 'Low',
        'open': 'Open',
        'Trading_Volume': 'Volume'   # ✅ 修正：原本錯誤寫成 'Revenue'
    }
    df = df.rename(columns=rename_map)

    # 確保欄位存在
    for col in ['Close', 'High', 'Low', 'Open']:
        if col not in df.columns:
            return 50, [f"⚠️ 缺少欄位 {col}"], pd.Series(), pd.Series()

    # 確保數值型態
    for col in ['Close', 'High', 'Low', 'Open']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'Volume' in df.columns:
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')

    df = df.dropna(subset=['Close'])

    if len(df) < 20:
        return 50, [], df.iloc[-1], df.iloc[-2]

    # RSI (14)
    diff = df['Close'].diff()
    gain = (diff.where(diff > 0, 0)).rolling(14).mean()
    loss = (-diff.where(diff < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.00001))))

    # KD (9, 3, 3)
    low9 = df['Low'].rolling(9).min()
    high9 = df['High'].rolling(9).max()
    rsv = 100 * ((df['Close'] - low9) / (high9 - low9 + 0.00001))
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()

    # MACD
    e12 = df['Close'].ewm(span=12, adjust=False).mean()
    e26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['OSC'] = (e12 - e26) - (e12 - e26).ewm(span=9, adjust=False).mean()

    # 布林 (20, 2)
    ma20 = df['Close'].rolling(20).mean()
    df['Upper'] = ma20 + (df['Close'].rolling(20).std() * 2)

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []

    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']:
        matches.append("🔥 KD低檔轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0:
        matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50:
        matches.append("📈 RSI強勢突破")
    if "布林通道" in m_list and last['Close'] > last['Upper']:
        matches.append("🌌 突破布林上軌")
    if "成交量" in m_list and 'Volume' in df.columns:
        vol_mean = df['Volume'].tail(5).mean()
        if vol_mean and last['Volume'] > vol_mean * 1.5:
            matches.append("📊 量能爆發")

    score = 50 + (len(matches) * 10) if last['Close'] >= prev['Close'] else 50 - (len(matches) * 5)
    return int(score), matches, last, prev


# ══════════════════════════════════════════════════════════
# 2. UI 樣式
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="台股極短線 AI 監控", layout="centered")

# ✅ 修正：將 CSS 獨立成變數，避免 Python 3.14 tokenizer 誤解 rgba 小數語法
_CSS = (
    "<style>"
    "html, body, [data-testid='stAppViewContainer'] { background-color: #0a0d14 !important; color: white; }"
    ".card { background:#111827; padding:20px; border-radius:12px; border-left:6px solid #38bdf8;"
    " margin-bottom:15px; border: 1px solid #1e2533; }"
    ".tag { background: #0e2233; color: #38bdf8; padding: 2px 8px; border-radius: 4px;"
    " font-size: 0.75rem; margin-right: 5px; border: 1px solid #1e4d6b; }"
    "</style>"
)
st.markdown(_CSS, unsafe_allow_html=True)

if "auth" not in st.session_state:
    st.session_state.auth = False
if "tk" not in st.session_state:
    st.session_state.tk = ""
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

# ══════════════════════════════════════════════════════════
# 登入驗證
# ══════════════════════════════════════════════════════════
if not st.session_state.auth:
    st.title("🛡️ 專業版授權驗證")
    t_input = st.text_input("輸入 FinMind Token", type="password")
    if st.button("驗證並開啟 AI 監控", use_container_width=True):
        check_df, msg = fetch_finmind_api("TaiwanStockInfo", None, t_input)
        if not check_df.empty:
            st.session_state.tk = t_input
            st.session_state.auth = True
            st.rerun()
        else:
            st.error(f"❌ 驗證失敗。原因：{msg}")
    st.stop()

# ══════════════════════════════════════════════════════════
# 3. 監控面板
# ══════════════════════════════════════════════════════════
st.title("⚡ AI 自動監控中")

with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect(
        "啟用指標",
        ["KD", "MACD", "RSI", "布林通道", "成交量"],
        default=["KD", "MACD", "RSI", "布林通道", "成交量"]
    )
    warn_p = st.slider("預警比例 (%)", 0.5, 5.0, 1.5)

    new_code = st.text_input("新增股票代碼")
    if st.button("➕ 加入監控"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            st.rerun()

    if st.button("🚪 登出系統"):
        st.session_state.auth = False
        st.rerun()


# 股票名稱快取
@st.cache_data(ttl=3600)
def get_name_map(token):
    df, _ = fetch_finmind_api("TaiwanStockInfo", None, token)
    return dict(zip(df['stock_id'], df['stock_name'])) if not df.empty else {}


name_map = get_name_map(st.session_state.tk)

# ══════════════════════════════════════════════════════════
# 顯示標的卡片
# ══════════════════════════════════════════════════════════
for code in list(st.session_state.watchlist):
    df, msg = fetch_finmind_api("TaiwanStockDaily", code, st.session_state.tk)

    if not df.empty and len(df) >= 2:
        c_name = name_map.get(code, f"個股 {code}")
        score, matches, last, prev = analyze_stock(df, m_list)

        if last.empty or prev.empty:
            st.warning(f"⚠️ {code}: 資料不足，無法分析")
            continue

        chg = (last['Close'] - prev['Close']) / prev['Close'] * 100

        color = "#ef4444" if chg > 0 else "#22c55e"
        tags_html = "".join([f'<span class="tag">{m}</span>' for m in matches])
        last_date = str(last.get('date', ''))[:10]

        st.markdown(f"""
        <div class="card" style="border-left-color: {color}">
            <div style="float:right; font-size:24px; font-weight:bold; color:{color}; border:2px solid {color}; border-radius:50%; width:50px; height:50px; display:flex; align-items:center; justify-content:center;">{score}</div>
            <div style="font-size:1rem; font-weight:bold;">{c_name} ({code}) <span style="font-size:0.7rem; color:#94a3b8;">[{last_date}]</span></div>
            <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:10px 0;">
                {last['Close']:.2f} <span style="font-size:1rem;">({chg:+.2f}%)</span>
            </div>
            <div><b>符合指標：</b><br>{tags_html if tags_html else "分析中..."}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
            st.session_state.watchlist.remove(code)
            st.rerun()
    else:
        st.warning(f"⚠️ {code}: 抓取失敗 ({msg})")

# ══════════════════════════════════════════════════════════
# ✅ 修正：自動刷新放在底部，並用 st.empty 控制，避免每次都 sleep 阻塞整個渲染
# ══════════════════════════════════════════════════════════
st.divider()
col1, col2 = st.columns([3, 1])
with col1:
    st.caption("⏱️ 每 60 秒自動刷新一次")
with col2:
    if st.button("🔄 立即刷新"):
        st.rerun()

# 使用 st.empty + time.sleep 做延遲刷新，不阻塞 UI
placeholder = st.empty()
for remaining in range(60, 0, -1):
    placeholder.caption(f"下次刷新倒數：{remaining} 秒")
    time.sleep(1)
placeholder.empty()
st.rerun()
