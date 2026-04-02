import streamlit as st
import pandas as pd
import requests
import time
import yfinance as yf
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# ══════════════════════════════════════════════════════════
# 1. 初始化設定與 Cookies 處理
# ══════════════════════════════════════════════════════════
controller = CookieController()
cookie_token = controller.get('finmind_token')

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
if not st.session_state.get("tk") and cookie_token:
    st.session_state.tk = cookie_token

# ══════════════════════════════════════════════════════════
# 2. 數據抓取邏輯 (支援中文名稱)
# ══════════════════════════════════════════════════════════
def is_trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    return now.replace(hour=9, minute=0) <= now <= now.replace(hour=13, minute=35)

def get_smart_data(code, token):
    """智慧切換數據源，並回傳 (DataFrame, 來源標記, 中文名稱)"""
    # 預設先處理代碼格式 (Yahoo 需要 .TW 或 .TWO)
    yf_code = code + ".TW" if len(code) == 4 else code + ".TWO"
    
    # 非交易時段或無 Token 用 Yahoo
    if not is_trading_time() or not token:
        try:
            ticker = yf.Ticker(yf_code)
            df = ticker.history(period="1mo")
            if not df.empty:
                name = ticker.info.get('shortName', '台股 ' + code)
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                return df.rename(columns={'high':'max', 'low':'min', 'volume':'volume'}), "Yahoo", name
        except: pass

    # 交易時段用 FinMind
    url = "https://api.finmindtrade.com/api/v4/data"
    start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
    headers = {"Authorization": "Bearer " + token}
    params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start_date}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        data = res.json().get("data", [])
        if data:
            df = pd.DataFrame(data)
            # 嘗試取得中文名稱 (從快照 API 或預設)
            name = data[0].get('stock_name', '個股 ' + code)
            return df.rename(columns={'Trading_Volume': 'volume'}), "FinMind", name
    except: pass
    return pd.DataFrame(), "Error", code

# ══════════════════════════════════════════════════════════
# 3. AI 分析邏輯 (五大指標判定)
# ══════════════════════════════════════════════════════════
def analyze_stock(df, m_list, warn_p):
    if df.empty or len(df) < 20: return 50, [], "數據不足", "載入中", "觀望", False
    df['close'] = pd.to_numeric(df['close'])
    
    # 指標計算
    diff = df['close'].diff()
    df['RSI'] = 100 - (100 / (1 + (diff.where(diff > 0, 0).rolling(14).mean() / (-diff.where(diff < 0, 0).rolling(14).mean() + 0.0001))))
    l9, h9 = df['min'].rolling(9).min(), df['max'].rolling(9).max()
    df['K'] = (100 * ((df['close'] - l9) / (h9 - l9 + 0.0001))).ewm(com=2, adjust=False).mean()
    ema12, ema26 = df['close'].ewm(span=12).mean(), df['close'].ewm(span=26).mean()
    df['OSC'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['Up'] = df['MA20'] + (df['close'].rolling(20).std() * 2)
    df['v_ma5'] = df['volume'].rolling(5).mean()

    last, prev = df.iloc[-1], df.iloc[-2]
    matches = []
    if "KD" in m_list and last['K'] < 35 and last['K'] > prev['K']: matches.append("🔥 KD轉強")
    if "MACD" in m_list and last['OSC'] > 0 and prev['OSC'] <= 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50 and prev['RSI'] <= 50: matches.append("📈 RSI走強")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5'] * 1.5: matches.append("📊 量能爆發")

    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    status, reason, strategy = "中性觀察", "尚無明顯突破訊號。", "觀望"
    if len(matches) >= 3 and chg > 0: status, reason, strategy = "多頭共振", "符合多項強勢指標，動能充足。", "強力續抱"
    elif last['close'] < last['MA20']: status, reason, strategy = "轉弱警訊", "跌破月線支撐，轉向守勢。", "減碼"

    return int(50 + len(matches)*10), matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# 4. 主介面 (補回新增功能、中文名稱、指標標籤)
# ══════════════════════════════════════════════════════════
st.set_page_config(page_title="AI 股市監控穩定版", layout="centered")

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

if not st.session_state.get("tk"):
    st.title("🛡️ 權限驗證")
    tk_input = st.text_input("輸入 Token", type="password")
    remember = st.checkbox("記住我的 Token")
    if st.button("登入"):
        st.session_state.tk = tk_input
        if remember: controller.set('finmind_token', tk_input, max_age=2592000)
        st.rerun()
    st.stop()

st.title("⚡ AI 自動監控面板")

# 側邊欄控制
with st.sidebar:
    st.header("⚙️ 參數設定")
    m_list = st.multiselect("啟用指標", ["KD", "MACD", "RSI", "布林通道", "成交量"], default=["KD", "MACD", "RSI", "布林通道", "成交量"])
    warn_p = st.slider("預警門檻 (%)", 0.5, 10.0, 1.5)
    
    st.divider()
    st.subheader("➕ 新增關注股票")
    new_code = st.text_input("輸入股票代碼 (如 2330)", placeholder="請輸入4-6位代碼")
    if st.button("確認新增"):
        if new_code and new_code not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_code.strip())
            st.success("已新增 " + new_code)
            st.rerun()
    
    st.divider()
    if st.button("🚪 登出系統"):
        controller.remove('finmind_token')
        st.session_state.tk = ""
        st.rerun()

# 顯示監控卡片
for code in list(st.session_state.watchlist):
    df, source, stock_name = get_smart_data(code, st.session_state.tk)
    if df.empty: continue

    score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)
    
    last_p = df.iloc[-1]['close']
    prev_p = df.iloc[-2]['close']
    chg = (last_p - prev_p) / prev_p * 100
    color = "#ef4444" if chg >= 0 else "#22c55e"
    
    # 組合 HTML
    html_card = '<div class="card" style="border-left-color: ' + color + '">'
    if is_warn: html_card += '<div class="warn-label">⚠️ 波動達 ' + str(warn_p) + '%</div>'
    
    html_card += '<div style="float:right; text-align:right;">'
    html_card += '<div style="color:'+color+'; font-size:1.3rem; font-weight:bold; border:2px solid '+color+'; border-radius:50%; width:45px; height:45px; display:flex; align-items:center; justify-content:center; margin-left:auto;">' + str(score) + '</div>'
    html_card += '<div style="margin-top:8px; font-weight:bold; color:#38bdf8; font-size:0.85rem;">' + strategy + '</div>'
    html_card += '</div>'
    
    html_card += '<div style="font-size:1rem; font-weight:bold;">' + stock_name + ' (' + code + ') <span style="font-size:0.7rem; color:#475569;">來源:' + source + '</span></div>'
    html_card += '<div style="font-size:1.8rem; font-weight:900; color:' + color + '; margin:10px 0;">' + f"{last_p:.2f}" + ' <span style="font-size:1rem;">(' + f"{chg:+.2f}" + '%)</span></div>'
    
    html_card += '<div class="dec-box">'
    html_card += '<div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">AI 決策：' + status + '</div>'
    html_card += '<div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">' + reason + '</div>'
    html_card += '</div>'
    
    # 符合指標標籤
    tags_html = "".join(['<span class="tag">' + m + '</span>' for m in matches])
    html_card += '<div>' + (tags_html if tags_html else '<span style="color:#475569; font-size:0.7rem;">掃描訊號中...</span>') + '</div>'
    html_card += '</div>'

    st.markdown(html_card, unsafe_allow_html=True)

    if st.button("🗑️ 移除 " + code, key="del_" + code):
        st.session_state.watchlist.remove(code)
        st.rerun()

st.divider()
if is_trading_time():
    st.caption("🟢 盤中更新中...")
    time.sleep(60); st.rerun()
else:
    st.caption("🔴 非交易時段 (Yahoo 模式)")
    if st.button("🔄 手動刷新"): st.rerun()
