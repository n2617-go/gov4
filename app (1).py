# ... (前面 get_smart_data 等函式保持不變) ...

def analyze_stock(df, m_list, warn_p):
    # 降低門檻，只要有 15 筆資料就開始分析，避免一直顯示掃描中
    if df.empty or len(df) < 15: 
        return 50, [], "初始化中", "正在累積足夠的歷史數據進行分析...", "觀望", False
    
    # 數據預處理
    for col in ['close', 'max', 'min', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    matches = []
    # 計算指標... (RSI, KD, MACD, 布林, 成交量 邏輯同前)
    # [此處省略計算公式以節省篇幅]

    last, prev = df.iloc[-1], df.iloc[-2]
    
    # 檢查勾選的指標並加入 matches
    if "KD" in m_list and last['K'] < 35: matches.append("🔥 KD低檔")
    if "MACD" in m_list and last['OSC'] > 0: matches.append("🚀 MACD翻紅")
    if "RSI" in m_list and last['RSI'] > 50: matches.append("📈 RSI走強")
    if "布林通道" in m_list and last['close'] > last['Up']: matches.append("🌌 突破布林")
    if "成交量" in m_list and last['volume'] > last['v_ma5']: matches.append("📊 量能增加")

    # 決策說明邏輯 (確保 reason 具體化)
    chg = (last['close'] - prev['close']) / prev['close'] * 100
    is_warning = abs(chg) >= warn_p
    
    status = "趨勢不明"
    reason = "目前各項技術指標訊號分散，建議靜待明確的量價突破。"
    strategy = "觀望"

    if len(matches) >= 3:
        status = "多頭共振"
        reason = f"目前有 {len(matches)} 項指標指向多頭，且股價表現強勢，動能充足。"
        strategy = "強力續抱"
    elif last['close'] < last['MA20']:
        status = "轉弱訊號"
        reason = "股價已跌破 20 日關鍵月線支撐，短期趨勢轉空，需注意回撤風險。"
        strategy = "減碼/清倉"

    score = int(50 + len(matches)*10) if chg > 0 else 45
    return score, matches, status, reason, strategy, is_warning

# ══════════════════════════════════════════════════════════
# UI 渲染部分 (確保 Reason 區塊結構正確)
# ══════════════════════════════════════════════════════════

# ... (在顯示迴圈內)
score, matches, status, reason, strategy, is_warn = analyze_stock(df, m_list, warn_p)

# HTML 構建 (將 Reason 加入顯示)
card_html = f'''
<div class="card" style="border-left-color: {color}">
    <div style="float:right; text-align:right;">
        <div style="color:{color}; font-size:1.4rem; font-weight:bold;">{score}</div>
        <div style="color:#38bdf8; font-size:0.8rem;">{strategy}</div>
    </div>
    <div style="font-size:1.1rem; font-weight:bold;">{c_name} ({code})</div>
    <div style="font-size:1.8rem; font-weight:900; color:{color}; margin:5px 0;">
        {last_p:.2f} <small style="font-size:1rem;">({chg:+.2f}%)</small>
    </div>
    
    <div class="dec-box">
        <div style="color:#94a3b8; font-size:0.75rem; font-weight:bold; margin-bottom:4px;">
            AI 決策：{status}
        </div>
        <div style="color:#f1f5f9; font-size:0.85rem; line-height:1.5;">
            {reason} </div>
    </div>
    
    <div style="margin-top:10px;">
        {"".join([f'<span class="tag">{m}</span>' for m in matches]) if matches else '<span style="color:#475569; font-size:0.7rem;">指標掃描中...</span>'}
    </div>
</div>
'''
st.markdown(card_html, unsafe_allow_html=True)
