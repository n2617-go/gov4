import streamlit as st
import pandas as pd
import yfinance as yf
import json
from streamlit_cookies_controller import CookieController

# 1. 建立控制器
controller = CookieController()

# 2. 核心：從 Cookie 初始化清單
# 這裡加一個 small delay 或檢查，確保 Cookie 讀取完成
cookie_watchlist = controller.get('user_watchlist')

if "watchlist" not in st.session_state:
    if cookie_watchlist:
        try:
            # 嘗試解析 Cookie 裡的 JSON 字串
            st.session_state.watchlist = json.loads(cookie_watchlist)
        except:
            st.session_state.watchlist = ["2330", "2317", "2603", "2454"]
    else:
        st.session_state.watchlist = ["2330", "2317", "2603", "2454"]

# --- 側邊欄新增股票的邏輯修正 ---
with st.sidebar:
    st.subheader("➕ 新增關注股票")
    new_code = st.text_input("輸入代碼", key="input_new_code")
    
    if st.button("確認新增"):
        if new_code and new_code not in st.session_state.watchlist:
            # 第一步：更新當前畫面狀態
            st.session_state.watchlist.append(new_code.strip())
            
            # 第二步：強制寫入 Cookie (設定有效期限 30 天)
            updated_list_json = json.dumps(st.session_state.watchlist)
            controller.set('user_watchlist', updated_list_json, max_age=2592000)
            
            st.success(f"已新增 {new_code} 並儲存至瀏覽器")
            time.sleep(0.5) # 給瀏覽器一點時間寫入
            st.rerun()

# --- 移除股票的邏輯修正 ---
# 在顯示卡片的迴圈中
    if st.button(f"🗑️ 移除 {code}", key=f"del_{code}"):
        st.session_state.watchlist.remove(code)
        
        # 同步更新 Cookie
        updated_list_json = json.dumps(st.session_state.watchlist)
        controller.set('user_watchlist', updated_list_json, max_age=2592000)
        
        st.rerun()
