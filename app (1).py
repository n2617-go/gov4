import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date
from streamlit_cookies_manager import EncryptedCookieManager

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控旗艦版", layout="centered")

# Cookie 加密金鑰（寫死版本，不影響不同使用者，各自瀏覽器獨立）
cookies = EncryptedCookieManager(
    prefix="stockapp_",
    password="stockapp-fixed-secret-key-2024"
)

if not cookies.ready():
    st.stop()

# ══════════════════════════════════════════════════════════
# 2. Cookie 讀取與初始化
# ══════════════════════════════════════════════════════════
DEFAULT_WATCHLIST = [
    {"code": "2330", "name": "台積電"},
    {"code": "2317", "name": "鴻海"},
    {"code": "2603", "name": "長榮"},
    {"code": "2454", "name": "聯發科"},
]

if "tk" not in st.session_state:
    saved_token = cookies.get("finmind_token", "")
    if saved_token:
        st.session_state.tk = saved_token

if "watchlist" not in st.session_state:
    saved_wl = cookies.get("user_watchlist", "")
    if saved_wl:
        try:
            loaded = json.loads(saved_wl)
            if loaded and isinstance(loaded[0], str):
                loaded = [{"code": c, "name": c} for c in loaded]
            st.session_state.watchlist = loaded
        except:
            st.session_state.watchlist = DEFAULT_WATCHLIST
    else:
        st.session_state.watchlist = DEFAULT_WATCHLIST


def save_watchlist():
    cookies["user_watchlist"] = json.dumps(
        st.session_state.watchlist, ensure_ascii=False
    )
    cookies.save()


# ══════════════════════════════════════════════════════════
# 3. 交易時間判斷
# ══════════════════════════════════════════════════════════
def is_trading_hours() -> bool:
    """判斷現在是否為台股交易時間（週一至五 09:00～13:30）"""
    now = datetime.now()
    # 週六(5)、週日(6) 不開盤
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    market_close = now.replace(hour=13, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


# ══════════════════════════════════════════════════════════
# 4. 資料抓取（即時 / 歷史 自動切換）
# ══════════════════════════════════════════════════════════

def get_realtime_price_finmind(code: str, token: str) -> dict | None:
    """
    開盤中：呼叫 FinMind TaiwanStockPriceTick（即時 snapshot）
    回傳 {"close": float, "volume": int, "name": str} 或 None
    """
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "dataset": "TaiwanStockPriceTick",
            "data_id": code,
            "start_date": str(date.today()),
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != 200 or not data.get("data"):
            return None
        df = pd.DataFrame(data["data"])
        if df.empty:
            return None
        last = df.iloc[-1]
        return {
            "close":  float(last.get("close", 0)),
            "volume": int(last.get("volume", 0)),
        }
    except:
        return None


def get_stock_name_finmind(code: str, token: str) -> str:
    """用 FinMind TaiwanStockInfo 抓中文名稱"""
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"dataset": "TaiwanStockInfo", "data_id": code}
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        data = resp.json()
        if data.get("status") == 200 and data.get("data"):
            return data["data"][0].get("stock_name", f"個股{code}")
    except:
        pass
    return f"個股{code}"


def get_history_finmind(code: str, token: str) -> pd.DataFrame:
    """用 FinMind TaiwanStockPrice 抓近 6 個月日線"""
    try:
        from datetime import timedelta
        start = (date.today() - timedelta(days=180)).strftime("%Y-%m-%d")
        url = "https://api.finmindtrade.com/api/v4/data"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": code,
            "start_date": start,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        if data.get("status") != 200 or not data.get("data"):
            return pd.DataFrame()
        df = pd.DataFrame(data["data"])
        df = df.rename(columns={
            "max": "max", "min": "min",
            "Trading_Volume": "volume"
        })
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"]).reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()


def get_stock_data(code: str):
    """
    主資料抓取入口：
    - 開盤中 + 有 token → FinMind 即時報價 + FinMind 歷史
    - 其他情況 → yfinance 歷史
    回傳 (df, name, is_realtime)
    """
    token = st.session_state.get("tk", "")
    trading = is_trading_hours()

    # ── 開盤中且有 Token：使用 FinMind ──
    if trading and token:
        # 歷史資料（用來計算指標）
        df = get_history_finmind(code, token)
        # 即時報價（覆蓋最後一筆）
        rt = get_realtime_price_finmind(code, token)
        if rt and not df.empty:
            # 將即時價格插入最後一列
            df.loc[df.index[-1], "close"]  = rt["close"]
            df.loc[df.index[-1], "volume"] = rt["volume"]
        # 抓名稱
        name = get_stock_name_finmind(code, token)
        if not df.empty:
            return df, name, True

    # ── 盤後 / 無 Token：使用 yfinance ──
    for suffix in [".TW", ".TWO"]:
        yf_code = code + suffix
        try:
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period="6mo")
            if df.empty:
                continue
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={"high": "max", "low": "min"})
            try:
                info = ticker.info
                raw_name = info.get("shortName") or info.get("longName") or ""
                name = raw_name.strip() if raw_name.strip() else f"個股{code}"
            except:
                name = f"個股{code}"
            return df, name, False
        except:
            continue

    return pd.DataFrame(), f"代碼{code}", False


# ══════════════════════════════════════════════════════════
# 5. 分析引擎
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20:
        return 50, [], "數據不足", "累積數據中...", "觀望", False

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    matches = []

    diff = df["close"].diff()
    gain = diff.where(diff > 0, 0).rolling(14).mean()
    loss = -diff.where(diff < 0, 0).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + (gain / (loss + 0.0001))))

    l9 = df["min"].rolling(9).min()
    h9 = df["max"].rolling(9).max()
    df["K"] = (100 * ((df["close"] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["OSC"] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()

    df["MA20"]  = df["close"].rolling(20).mean()
    df["Up"]    = df["MA20"] + (df["close"].rolling(20).std() * 2)
    df["v_ma5"] = df["volume"].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]

    if "KD"     in m_list and last["K"] < 35 and last["K"] > prev["K"]:       matches.append("🔥 KD轉強")
    if "MACD"   in m_list and last["OSC"] > 0 and prev["OSC"] <= 0:           matches.append("🚀 MACD翻紅")
    if "RSI"    in m_list and last["RSI"] > 50 and prev["RSI"] <= 50:         matches.append("📈 RSI強勢")
    if "布林通道" in m_list and last["close"] > last["Up"]:                    matches.append("🌌 突破布林")
    if "成交量"  in m_list and last["volume"] > last["v_ma5"] * 1.5:          matches.append("📊 量能爆發")

    chg = (last["close"] - prev["close"]) / prev["close"] * 100
    is_warning = abs(chg) >= warn_p

    status, strategy = "中性觀察", "觀望"
    reason = "目前多空訊號不明，建議靜待突破。"
    if len(matches) >= 3 and chg > 0:
        status, strategy = "多頭共振", "強力續抱"
        reason = f"符合 {len(matches)} 項指標，股價動能極強。"
    elif last["close"] < last["MA20"]:
        status, strategy = "轉弱訊號", "減碼規避"
        reason = "股價跌破月線，短期趨勢轉空。"

    score = int(50 + len(matches) * 10)
    return score, matches, status, reason, strategy, is_warning


# ══════════════════════════════════════════════════════════
# 6. 登入阻擋
# ══════════════════════════════════════════════════════════
if not st.session_state.get("tk"):
    st.title("🛡️ 專業監控系統登入")
    st.info("請輸入您的 FinMind API Token。開盤時間將使用即時資料，盤後使用歷史資料。")
    tk_input = st.text_input("FinMind API Token", type="password")
    if st.button("驗證並登入"):
        if tk_input:
            st.session_state.tk = tk_input
            cookies["finmind_token"] = tk_input
            cookies.save()
            st.success("登入成功！正在載入數據...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("請輸入正確的 Token")
    st.stop()


# ══════════════════════════════════════════════════════════
# 7. 主 UI
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0a0d14; color: white; }
    .card {
        background: #111827;
        padding: 20px;
        border-radius: 12px;
        border-left: 6px solid #38bdf8;
        margin-bottom: 15px;
        border: 1px solid #1e2533;
        position: relative;
    }
    .dec-box {
        background: #0f172a;
        padding: 12px;
        border-radius: 8px;
        margin: 10px 0;
        border: 1px solid #1e293b;
    }
    .tag {
        background: #1e293b;
        color: #38bdf8;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 5px;
        border: 1px solid #334155;
    }
    .warn-label {
        background: #facc15;
        color: #000;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.7rem;
        font-weight: bold;
        position: absolute;
        top: 10px;
        right: 20px;
    }
    .rt-badge {
        background: #16a34a;
        color: #fff;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.65rem;
        font-weight: bold;
        margin-left: 6px;
        vertical-align: middle;
    }
    .delay-badge {
        background: #475569;
        color: #cbd5e1;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.65rem;
        margin-left: 6px;
        vertical-align: middle;
    }
</style>
""", unsafe_allow_html=True)

# ── 側邊欄 ──
with st.sidebar:
    st.header("⚙️ 控制中心")

    # 顯示目前資料來源狀態
    if is_trading_hours():
        st.success("🟢 開盤中 · 使用 FinMind 即時資料")
    else:
        st.info("🔵 盤後 · 使用 yfinance 歷史資料")

    m_list = st.multiselect(
        "啟用指標",
        ["KD", "MACD", "RSI", "布林通道", "成交量"],
        default=["KD", "MACD", "RSI", "布林通道", "成交量"]
    )
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)

    st.divider()
    new_code = st.text_input("➕ 新增代碼")
    if st.button("確認新增"):
        code_clean = new_code.strip().upper()
        existing_codes = [item["code"] for item in st.session_state.watchlist]
        if not code_clean:
            st.warning("請輸入股票代碼")
        elif code_clean in existing_codes:
            st.warning(f"{code_clean} 已在清單中")
        else:
            with st.spinner(f"正在查詢 {code_clean}..."):
                tmp_df, tmp_name, _ = get_stock_data(code_clean)
            if tmp_df.empty:
                st.error(f"找不到代碼 {code_clean}，請確認代碼是否正確")
            else:
                st.session_state.watchlist.append({"code": code_clean, "name": tmp_name})
                save_watchlist()
                st.rerun()

    st.divider()
    if st.button("🚪 登出系統"):
        cookies["finmind_token"] = ""
        cookies.save()
        st.session_state.tk = None
        st.rerun()

# ── 主面板 ──
now_str = datetime.now().strftime("%H:%M:%S")
st.title("⚡ AI 自動監控面板")
st.caption(f"資料更新時間：{now_str}　{'🟢 即時報價（FinMind）' if is_trading_hours() else '🔵 盤後歷史資料（yfinance）'}")

need_save = False

for item in list(st.session_state.watchlist):
    code   = item["code"]
    c_name = item.get("name", code)

    df, fetched_name, is_realtime = get_stock_data(code)

    if c_name == code or c_name.startswith("個股") or c_name.startswith("代碼"):
        item["name"] = fetched_name
        c_name = fetched_name
        need_save = True

    if df.empty:
        st.warning(f"⚠️ 無法抓取 {code}")
        continue

    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    last_p = df.iloc[-1]["close"]
    prev_p = df.iloc[-2]["close"]
    chg    = (last_p - prev_p) / prev_p * 100
    color  = "#ef4444" if chg >= 0 else "#22c55e"

    badge_html = '<span class="rt-badge">即時</span>' if is_realtime else '<span class="delay-badge">盤後</span>'
    warn_html  = f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>' if is_warn else ''
    tags_html  = (
        " ".join([f'<span class="tag">{m}</span>' for m in matches])
        if matches else '<span style="color:#475569; font-size:0.7rem;">掃描訊號中...</span>'
    )

    html_card = (
        '<div class="card" style="border-left-color: ' + color + '">'
        + warn_html
        + '<div style="float:right; text-align:right;">'
        + '<div style="color:' + color + '; font-size:1.5rem; font-weight:bold;">' + str(score) + '</div>'
        + '<div style="color:#38bdf8; font-size:0.85rem; font-weight:bold;">' + strategy + '</div>'
        + '</div>'
        + '<div style="font-size:1.1rem; font-weight:bold;">' + c_name + '（' + code + '）' + badge_html + '</div>'
        + '<div style="font-size:2rem; font-weight:900; color:' + color + '; margin:10px 0;">'
        + f'{last_p:.2f} <small style="font-size:1rem;">({chg:+.2f}%)</small>'
        + '</div>'
        + '<div class="dec-box">'
        + '<div style="color:#94a3b8; font-size:0.75rem; font-weight:bold;">AI 決策：' + status + '</div>'
        + '<div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">' + reason + '</div>'
        + '</div>'
        + '<div>' + tags_html + '</div>'
        + '</div>'
    )

    st.markdown(html_card, unsafe_allow_html=True)

    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist = [i for i in st.session_state.watchlist if i["code"] != code]
        save_watchlist()
        st.rerun()

if need_save:
    save_watchlist()

# ── 開盤中自動 60 秒刷新 ──
if is_trading_hours():
    time.sleep(1)
    st.rerun()
