import streamlit as st
import pandas as pd
import yfinance as yf
import json
import time
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 系統初始化
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控旗艦版", layout="centered")

controller = CookieController()

# ──────────────────────────────────────────────────────────
# 【修正一】Cookie 讀取需等待一個 rerun 才能正確取值
# 用 _loaded 旗標確保只初始化一次，避免每次 rerun 都重置
# ──────────────────────────────────────────────────────────
if "_loaded" not in st.session_state:
    st.session_state._loaded = False
    st.rerun()

if not st.session_state._loaded:
    cookie_token     = controller.get('finmind_token')
    cookie_watchlist = controller.get('user_watchlist')

    if "tk" not in st.session_state and cookie_token:
        st.session_state.tk = cookie_token

    # 【修正二】watchlist 改存 list of dict，格式：
    # [{"code": "2330", "name": "台積電"}, ...]
    # 名稱一併存入 cookie，重開頁面也不需重新抓取
    DEFAULT_WATCHLIST = [
        {"code": "2330", "name": "台積電"},
        {"code": "2317", "name": "鴻海"},
        {"code": "2603", "name": "長榮"},
        {"code": "2454", "name": "聯發科"},
    ]

    if "watchlist" not in st.session_state:
        if cookie_watchlist:
            try:
                loaded = json.loads(cookie_watchlist)
                # 相容舊格式（純字串列表）自動升級
                if loaded and isinstance(loaded[0], str):
                    loaded = [{"code": c, "name": c} for c in loaded]
                st.session_state.watchlist = loaded
            except:
                st.session_state.watchlist = DEFAULT_WATCHLIST
        else:
            st.session_state.watchlist = DEFAULT_WATCHLIST

    st.session_state._loaded = True


def save_watchlist():
    """新增/刪除後呼叫，立即寫回 cookie（30天）"""
    controller.set(
        'user_watchlist',
        json.dumps(st.session_state.watchlist, ensure_ascii=False),
        max_age=2592000
    )


# ══════════════════════════════════════════════════════════
# 2. 資料抓取
# ══════════════════════════════════════════════════════════
def get_stock_data(code):
    """先試 .TW 再試 .TWO；name 抓取獨立 try/except 避免 timeout"""
    for suffix in [".TW", ".TWO"]:
        yf_code = code + suffix
        try:
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period="6mo")
            if df.empty:
                continue
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={'high': 'max', 'low': 'min'})

            try:
                info = ticker.info
                # shortName 通常含中文（如「台積電」），優先使用
                raw_name = info.get('shortName') or info.get('longName') or ""
                name = raw_name.strip() if raw_name.strip() else f"個股{code}"
            except:
                name = f"個股{code}"

            return df, name
        except:
            continue
    return pd.DataFrame(), f"代碼{code}"


# ══════════════════════════════════════════════════════════
# 3. 分析引擎
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20:
        return 50, [], "數據不足", "累積數據中...", "觀望", False

    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    matches = []

    diff = df['close'].diff()
    gain = diff.where(diff > 0, 0).rolling(14).mean()
    loss = -diff.where(diff < 0, 0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / (loss + 0.0001))))

    l9 = df['min'].rolling(9).min()
    h9 = df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()

    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()

    df['MA20']  = df['close'].rolling(20).mean()
    df['Up']    = df['MA20'] + (df['close'].rolling(20).std() * 2)
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]

    if "KD"     in m_list and last['K'] < 35 and last['K'] > prev['K']:      matches.append("🔥 KD轉強")
    if "MACD"   in m_list and last['OSC'] > 0 and prev['OSC'] <= 0:          matches.append("🚀 MACD翻紅")
    if "RSI"    in m_list and last['RSI'] > 50 and prev['RSI'] <= 50:        matches.append("📈 RSI強勢")
    if "布林通道" in m_list and last['close'] > last['Up']:                   matches.append("🌌 突破布林")
    if "成交量"  in m_list and last['volume'] > last['v_ma5'] * 1.5:         matches.append("📊 量能爆發")

    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p

    status, strategy = "中性觀察", "觀望"
    reason = "目前多空訊號不明，建議靜待突破。"
    if len(matches) >= 3 and chg > 0:
        status, strategy = "多頭共振", "強力續抱"
        reason = f"符合 {len(matches)} 項指標，股價動能極強。"
    elif last['close'] < last['MA20']:
        status, strategy = "轉弱訊號", "減碼規避"
        reason = "股價跌破月線，短期趨勢轉空。"

    score = int(50 + len(matches) * 10)
    return score, matches, status, reason, strategy, is_warning


# ══════════════════════════════════════════════════════════
# 4. 登入阻擋
# ══════════════════════════════════════════════════════════
if not st.session_state.get("tk"):
    st.title("🛡️ 專業監控系統登入")
    tk_input = st.text_input("請輸入授權 Token", type="password")
    if st.button("驗證並登入"):
        if tk_input:
            st.session_state.tk = tk_input
            controller.set('finmind_token', tk_input, max_age=2592000)
            st.success("登入成功！正在載入數據...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("請輸入正確的 Token")
    st.stop()


# ══════════════════════════════════════════════════════════
# 5. 主 UI
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
</style>
""", unsafe_allow_html=True)

# ── 側邊欄 ──
with st.sidebar:
    st.header("⚙️ 控制中心")
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
                tmp_df, tmp_name = get_stock_data(code_clean)
            if tmp_df.empty:
                st.error(f"找不到代碼 {code_clean}，請確認代碼是否正確")
            else:
                st.session_state.watchlist.append({"code": code_clean, "name": tmp_name})
                save_watchlist()  # 立即寫入 cookie
                st.rerun()

    st.divider()
    if st.button("🚪 登出系統"):
        controller.remove('finmind_token')
        st.session_state.tk = None
        st.rerun()

# ── 主面板 ──
st.title("⚡ AI 自動監控面板")

need_save = False  # 用於批次更新名稱後統一儲存

for item in list(st.session_state.watchlist):
    code   = item["code"]
    c_name = item.get("name", code)

    df, fetched_name = get_stock_data(code)

    # 若儲存的名稱還是佔位符，用最新抓到的更新並存回 cookie
    if c_name == code or c_name.startswith("個股") or c_name.startswith("代碼"):
        item["name"] = fetched_name
        c_name = fetched_name
        need_save = True

    if df.empty:
        st.warning(f"⚠️ 無法抓取 {code}")
        continue

    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg    = (last_p - prev_p) / prev_p * 100
    color  = "#ef4444" if chg >= 0 else "#22c55e"

    warn_html = f'<div class="warn-label">⚠️ 波動達 {warn_p}%</div>' if is_warn else ''
    tags_html = (
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
        + '<div style="font-size:1.1rem; font-weight:bold;">' + c_name + '（' + code + '）</div>'
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
        save_watchlist()  # 立即寫入 cookie
        st.rerun()

# 若有名稱被更新，統一儲存一次
if need_save:
    save_watchlist()
