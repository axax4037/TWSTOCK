#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股全方位戰情室 - Streamlit 版本
功能包含：
1. 即時戰情監控
2. 技術分析（SMA、RSI、KD）
3. 策略回測
4. 大單監控
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fubon_neo.sdk import FubonSDK
from datetime import datetime, timedelta

# ==========================================
# 1. 頁面基本設定與狀態初始化
# ==========================================
st.set_page_config(page_title="台股全方位戰情室", layout="wide", page_icon="📈")

if 'fubon_sdk' not in st.session_state:
    st.session_state.fubon_sdk = None
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False

# ==========================================
# 2. 側邊欄：系統連線與動態標的設定
# ==========================================
st.sidebar.title("⚙️ 系統設定與連線")
st.sidebar.markdown("---")

user_id = st.sidebar.text_input("身分證字號", type="password")
password = st.sidebar.text_input("登入密碼", type="password")
cert_path = st.sidebar.text_input("憑證路徑", value=r"D:\Users\MHChen\Desktop\您的身分證字號_20270414富邦憑證.p12")
cert_password = st.sidebar.text_input("憑證密碼", type="password")

if st.sidebar.button("🔌 連線富邦 API"):
    with st.spinner("連線中..."):
        try:
            sdk = FubonSDK()
            res = sdk.login(user_id, password, cert_path, cert_password)
            if res.is_success:
                # 關鍵：必須初始化行情模組
                sdk.init_realtime()
                st.session_state.fubon_sdk = sdk
                st.session_state.is_logged_in = True
                st.sidebar.success("✅ 連線成功！")
            else:
                st.sidebar.error(f"❌ 登入失敗：{res.message}")
        except Exception as e:
            st.sidebar.error(f"連線發生錯誤：{e}")

st.sidebar.markdown("---")
st.sidebar.title("🎯 標的選擇與監控")
target_symbol = st.sidebar.text_input("請輸入台股代碼 (例如：2317, 2881)", value="2330")

# ==========================================
# 3. 核心資料處理函式 (純 Pandas 實作指標)
# ==========================================
def calculate_indicators_manual(df):
    """不依賴 pandas-ta，使用純 pandas 手動計算指標"""
    df = df.copy()
    
    # 1. 均線 SMA 20
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    
    # 2. 相對強弱指標 RSI 14
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # 3. 隨機指標 KD (9,3,3)
    min_low = df['low'].rolling(window=9).min()
    max_high = df['high'].rolling(window=9).max()
    rsv = (df['close'] - min_low) / (max_high - min_low + 1e-10) * 100 
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    return df.dropna()

@st.cache_data(ttl=60) # 快取 60 秒確保資料即時
def fetch_and_analyze_data(symbol, _sdk):
    now = datetime.now()
    start_date = (now - timedelta(days=200)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        # 正確調用 candles API
        kline_res = _sdk.marketdata.rest_client.stock.historical.candles(**{
            "symbol": symbol,
            "from": start_date,
            "to": end_date,
            "fields": "open,high,low,close,volume"
        })
        
        if not kline_res or 'data' not in kline_res or len(kline_res['data']) == 0:
            st.error(f"⚠️ API 未回傳 {symbol} 的數據，請確認代號正確或稍後再試。")
            return None
            
        df = pd.DataFrame(kline_res['data'])
        
        # 處理日期欄位名稱差異
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
        elif 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)

        df = df.sort_index()
        df = calculate_indicators_manual(df)
        
        last_date = df.index[-1].strftime('%Y-%m-%d')
        st.sidebar.info(f"📅 數據最後更新日期：{last_date}")
        return df
        
    except Exception as e:
        st.error(f"抓取數據失敗：{e}")
        return None

def plot_candlestick(df, title):
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='K 線')])
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#FFA500', width=2), name='20MA'))
    fig.update_layout(title=title, xaxis_rangeslider_visible=False, template='plotly_dark')
    return fig

# ==========================================
# 4. 主畫面佈局
# ==========================================
st.title("📊 台股全方位追蹤面板")

if not st.session_state.is_logged_in:
    st.warning("請先由左側面板輸入憑證資訊並連線 API。")
    st.stop()

with st.spinner(f"正在載入 {target_symbol} 歷史大數據與運算模型..."):
    df = fetch_and_analyze_data(target_symbol, st.session_state.fubon_sdk)

if df is None or df.empty:
    st.stop()

latest = df.iloc[-1]
suggested_threshold = 50 if latest['close'] < 100 else 10
large_order_vol = st.sidebar.number_input("🚨 即時大單門檻 (張)", value=suggested_threshold, min_value=1)

tab1, tab2, tab3 = st.tabs(["⚡ 即時戰情", "🧠 技術分析", "💰 策略回測"])

# --- 分頁 1：即時戰情 ---
with tab1:
    col1, col2, col3 = st.columns(3)
    col1.metric("今日收盤價", f"{latest['close']:.2f}")
    col2.metric("預估全日量能", f"{int(latest['volume'] * 1.15)} 張")
    col3.metric("距漲停空間", f"{((latest['close']*1.1 - latest['close'])/latest['close']*100):.1f}%")
    
    st.markdown(f"### 🚨 {target_symbol} 即時大單監控預留區 (> {large_order_vol} 張)")
    st.info("背景 WebSocket 監聽啟動後，當偵測到大單將於此處跳出提示。")

# --- 分頁 2：技術分析 ---
with tab2:
    is_uptrend = latest['close'] > latest['SMA_20']
    rsi = latest['RSI_14']
    
    if is_uptrend and rsi > 50:
        signal, color = "🟢 強勢偏多 (符合多頭條件)", "normal"
    elif not is_uptrend and rsi < 50:
        signal, color = "🔴 弱勢偏空 (符合空頭條件)", "inverse"
    else:
        signal, color = "⚪ 震盪整理 (建議觀望)", "off"
        
    st.metric(f"💡 {target_symbol} 明日操作訊號", signal, delta_color=color)
    st.plotly_chart(plot_candlestick(df, f"{target_symbol} 近期走勢與 20MA"), use_container_width=True)

# --- 分頁 3：策略回測 ---
with tab3:
    test_df = df.copy()
    test_df['signal'] = 0
    
    for i in range(1, len(test_df)):
        if test_df['close'].iloc[i] > test_df['SMA_20'].iloc[i] and (test_df['K'].iloc[i-1] < test_df['D'].iloc[i-1] and test_df['K'].iloc[i] > test_df['D'].iloc[i]):
            test_df.at[test_df.index[i], 'signal'] = 1
        elif test_df['close'].iloc[i] < test_df['SMA_20'].iloc[i] or (test_df['K'].iloc[i-1] > test_df['D'].iloc[i-1] and test_df['K'].iloc[i] < test_df['D'].iloc[i]):
            test_df.at[test_df.index[i], 'signal'] = -1

    position = 0
    profits = []
    equity_curve = [100000] 
    
    for date, row in test_df.iterrows():
        if row['signal'] == 1 and position == 0:
            position = row['close']
        elif row['signal'] == -1 and position != 0:
            profit = (row['close'] - position) / position
            profits.append(profit)
            equity_curve.append(equity_curve[-1] * (1 + profit))
            position = 0
            
    win_rate = (len([p for p in profits if p > 0]) / len(profits) * 100) if profits else 0
    total_return = (equity_curve[-1] - 100000) / 1000
    
    col1, col2, col3 = st.columns(3)
    col1.metric("總進出場次數", f"{len(profits)} 次")
    col2.metric("策略模擬勝率", f"{win_rate:.1f} %")
    col3.metric("累積報酬率", f"{total_return:.1f} %")
    
    st.markdown("### 💵 資產增長曲線 (初始資金 10 萬)")
    st.line_chart(equity_curve)
