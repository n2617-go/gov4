# 3. 渲染清單
for code in list(st.session_state.watchlist):
    # --- 修正處：檢查 snapshot_df 是否為空，並使用正確的欄位名稱 data_id ---
    if snapshot_df.empty:
        st.warning("⚠️ 無法取得即時行情，請檢查 Token 或稍後再試")
        break

    # FinMind 快照 API 的股票代碼欄位通常是 'data_id'
    stock_snap = snapshot_df[snapshot_df['data_id'] == code]
    
    if stock_snap.empty:
        st.info(f"🔍 找不到 {code} 的即時資料，跳過分析")
        continue
    
    snap = stock_snap.iloc[0]
    
    # 抓取歷史數據做 AI 分析 (快取處理)
    @st.cache_data(ttl=3600)
    def get_hist(c, t):
        # 歷史價格 API 使用的是 stock_id
        return fetch_finmind("TaiwanStockPrice", c, t, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
    
    hist_df = get_hist(code, st.session_state.tk)
    
    # 確保歷史資料抓取成功再進行分析
    if not hist_df.empty:
        score, matches, status, reason, strategy = analyze_logic(hist_df, m_list)
        
        # 取得價格與漲跌幅 (快照 API 的欄位名: last, change_rate)
        current_price = float(snap.get('last', 0))
        chg = float(snap.get('change_rate', 0))
        # ... 接下來的 HTML 渲染代碼保持不變 ...
