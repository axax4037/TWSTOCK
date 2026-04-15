#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股全方位戰情室 - 進階完整版
功能：
1. 即時戰情（今日數據）
2. 昨日數據回顧
3. 技術分析（含酒田戰法）
4. 策略回測（可自訂參數）
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fubon_neo.sdk import FubonSDK
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. 頁面設定與狀態初始化
# ==========================================
st.set_page_config(page_title="台股全方位戰情室 (進階版)", layout="wide", page_icon="📈")

if 'fubon_sdk' not in st.session_state:
    st.session_state.fubon_sdk = None
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False
if 'stock_info' not in st.session_state:
    st.session_state.stock_info = {}

# ==========================================
# 2. 酒田戰法偵測函式
# ==========================================
def detect_sakata_patterns(df):
    """偵測酒田戰法基本形態"""
    df = df.copy()
    df['pattern'] = ''
    df['sakata_signal'] = 0
    
    for i in range(2, len(df)):
        curr = df.iloc[i]
        prev1 = df.iloc[i-1]
        prev2 = df.iloc[i-2]
        
        def is_yang(row): return row['close'] > row['open']
        def is_yin(row): return row['close'] < row['open']
        def body_size(row): return abs(row['close'] - row['open'])
        def upper_shadow(row): return row['high'] - max(row['open'], row['close'])
        def lower_shadow(row): return min(row['open'], row['close']) - row['low']
        
        # 三陽 (Three White Soldiers)
        if is_yang(curr) and is_yang(prev1) and is_yang(prev2) and \
           curr['close'] > prev1['close'] > prev2['close']:
            df.at[curr.name, 'pattern'] = '🟢 三陽 (強多)'
            df.at[curr.name, 'sakata_signal'] = 1
            
        # 三陰 (Three Black Crows)
        elif is_yin(curr) and is_yin(prev1) and is_yin(prev2) and \
             curr['close'] < prev1['close'] < prev2['close']:
            df.at[curr.name, 'pattern'] = '🔴 三陰 (強空)'
            df.at[curr.name, 'sakata_signal'] = -1
            
        # 錘子 (Hammer)
        elif body_size(curr) * 3 <= (curr['high'] - curr['low']) and \
             lower_shadow(curr) > body_size(curr) * 2 and \
             upper_shadow(curr) < body_size(curr) * 0.5:
            df.at[curr.name, 'pattern'] = '🔨 錘子 (看漲)'
            df.at[curr.name, 'sakata_signal'] = 1
            
        # 上吊 (Hanging Man)
        elif body_size(curr) * 3 <= (curr['high'] - curr['low']) and \
             lower_shadow(curr) > body_size(curr) * 2 and \
             upper_shadow(curr) < body_size(curr) * 0.5 and \
             curr['close'] > df.iloc[max(0,i-5):i]['close'].mean():
            df.at[curr.name, 'pattern'] = '🪢 上吊 (看跌)'
            df.at[curr.name, 'sakata_signal'] = -1
            
        # 十字星 (Doji)
        elif body_size(curr) < (curr['high'] - curr['low']) * 0.1:
            df.at[curr.name, 'pattern'] = '✚ 十字星 (變盤)'
            
    return df

# ==========================================
# 3. 技術指標計算
# ==========================================
def calculate_indicators(df):
    """計算所有技術指標"""
    df = df.copy()
    
    # 均線
    df['SMA_5'] = df['close'].rolling(window=5).mean()
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['SMA_60'] = df['close'].rolling(window=60).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # KD
    min_low = df['low'].rolling(window=9).min()
    max_high = df['high'].rolling(window=9).max()
    rsv = (df['close'] - min_low) / (max_high - min_low + 1e-10) * 100
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # 酒田戰法
    df = detect_sakata_patterns(df)
    
    return df.dropna()

# ==========================================
# 4. 資料抓取
# ==========================================
@st.cache_data(ttl=30)
def fetch_data(symbol, sdk, days=200):
    """抓取歷史 K 線"""
    now = datetime.now()
    start_date = (now - timedelta(days=days)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        kline_res = sdk.marketdata.rest_client.stock.historical.candles(**{
            "symbol": symbol,
            "from": start_date,
            "to": end_date,
            "fields": "open,high,low,close,volume"
        })
        
        if not kline_res or 'data' not in kline_res or len(kline_res['data']) == 0:
            return None, "無數據"
            
        df = pd.DataFrame(kline_res['data'])
        date_col = 'date' if 'date' in df.columns else 'time'
        df[date_col] = pd.to_datetime(df[date_col])
        df.set_index(date_col, inplace=True)
        df = df.sort_index()
        df = calculate_indicators(df)
        
        return df, "成功"
    except Exception as e:
        return None, str(e)

# ==========================================
# 5. 側邊欄設定
# ==========================================
st.sidebar.title("⚙️ 系統設定")
st.sidebar.markdown("---")

user_id = st.sidebar.text_input("身分證字號", type="password", key="uid")
password = st.sidebar.text_input("登入密碼", type="password", key="pwd")
cert_path = st.sidebar.text_input("憑證路徑", value=r"D:\Users\MHChen\Desktop\您的憑證.p12", key="cert")
cert_password = st.sidebar.text_input("憑證密碼", type="password", key="certpwd")

if st.sidebar.button("🔌 連線富邦 API"):
    with st.spinner("連線中..."):
        try:
            sdk = FubonSDK()
            res = sdk.login(user_id, password, cert_path, cert_password)
            if res.is_success:
                sdk.init_realtime()
                st.session_state.fubon_sdk = sdk
                st.session_state.is_logged_in = True
                st.sidebar.success("✅ 連線成功！")
                st.rerun()
            else:
                st.sidebar.error(f"❌ 登入失敗：{res.message}")
        except Exception as e:
            st.sidebar.error(f"錯誤：{e}")

st.sidebar.markdown("---")
st.sidebar.title("🎯 標的選擇")

target_symbol = st.sidebar.text_input("輸入台股代號", value="2330", key="symbol")

# 查詢股票名稱（簡化版，實際需透過 API）
stock_name = st.session_state.stock_info.get(target_symbol, "")
if target_symbol and st.session_state.is_logged_in and target_symbol not in st.session_state.stock_info:
    # 這裡可以呼叫 API 查詢名稱，暫時用模擬
    st.session_state.stock_info[target_symbol] = f"股票{target_symbol}"
    stock_name = st.session_state.stock_info[target_symbol]

if stock_name:
    st.sidebar.info(f"🏷️ {target_symbol} {stock_name}")
else:
    st.sidebar.info(f"🏷️ {target_symbol}")

# ==========================================
# 6. 主程式
# ==========================================
st.title(f"📊 台股全方位戰情室：{target_symbol} {stock_name if stock_name else ''}")

if not st.session_state.is_logged_in:
    st.warning("⚠️ 請先由左側面板輸入憑證資訊並連線 API。")
    st.stop()

with st.spinner(f"載入 {target_symbol} 數據中..."):
    df, status = fetch_data(target_symbol, st.session_state.fubon_sdk, days=200)

if df is None or df.empty:
    st.error(f"❌ 無法取得數據：{status}")
    st.stop()

# 分離今日與昨日數據
latest = df.iloc[-1]
yesterday = df.iloc[-2] if len(df) > 1 else latest
last_date = df.index[-1].strftime('%Y-%m-%d')
yesterday_date = df.index[-2].strftime('%Y-%m-%d') if len(df) > 1 else last_date

st.sidebar.info(f"📅 最新數據日期：{last_date}")

# 分頁設定
tab1, tab2, tab3, tab4 = st.tabs(["⚡ 即時戰情 (今日)", "📅 昨日數據回顧", "🧠 技術分析 (酒田戰法)", "💰 策略回測"])

# --- Tab 1: 即時戰情 ---
with tab1:
    st.header(f"⚡ {target_symbol} {stock_name} - 今日戰情 ({last_date})")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("今日收盤價", f"{latest['close']:.2f}", delta=f"{latest['close'] - yesterday['close']:.2f}")
    col2.metric("今日成交量", f"{int(latest['volume']):,} 張")
    col3.metric("今日漲跌幅", f"{((latest['close']/yesterday['close'])-1)*100:.2f}%", 
                delta_color="normal" if ((latest['close']/yesterday['close'])-1) >= 0 else "inverse")
    col4.metric("預估全日量能", f"{int(latest['volume'] * 1.15):,} 張")
    
    st.markdown("### 📊 今日 K 線型態")
    if latest['pattern']:
        st.info(f"🎯 {latest['pattern']}")
    else:
        st.info("無特殊型態")
    
    # 五檔操作建議
    is_uptrend = latest['close'] > latest['SMA_20']
    rsi = latest['RSI_14']
    kd_golden = latest['K'] > latest['D'] and df.iloc[-2]['K'] <= df.iloc[-2]['D']
    
    if is_uptrend and rsi > 50 and kd_golden:
        signal = "🟢 強勢偏多 - 建議買進/持有"
    elif is_uptrend and rsi > 50:
        signal = "🟡 溫和偏多 - 觀望或加碼"
    elif not is_uptrend and rsi < 50:
        signal = "🔴 弱勢偏空 - 建議賣出/觀望"
    elif not is_uptrend and rsi < 40:
        signal = "🟣 極度偏空 - 可能超賣"
    else:
        signal = "⚪ 震盪整理 - 建議觀望"
    
    st.metric("💡 操作建議", signal)

# --- Tab 2: 昨日數據 ---
with tab2:
    st.header(f"📅 {target_symbol} - 昨日數據回顧 ({yesterday_date})")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("昨日收盤價", f"{yesterday['close']:.2f}")
    col2.metric("昨日成交量", f"{int(yesterday['volume']):,} 張")
    col3.metric("昨日 K 線型態", yesterday['pattern'] if yesterday['pattern'] else "一般")
    
    st.markdown("### 近 5 日走勢")
    recent_df = df.tail(5)
    st.dataframe(recent_df[['open', 'high', 'low', 'close', 'volume', 'pattern']].style.format({
        'open': '{:.2f}', 'high': '{:.2f}', 'low': '{:.2f}', 'close': '{:.2f}', 'volume': '{:,.0f}'
    }))

# --- Tab 3: 技術分析 ---
with tab3:
    st.header(f"🧠 {target_symbol} - 技術分析與酒田戰法")
    
    # K 線圖
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='K線')])
    
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#FFA500', width=2), name='20MA'))
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_5'], line=dict(color='#00FFFF', width=1), name='5MA'))
    
    # 標註酒田訊號
    buy_signals = df[df['sakata_signal'] == 1]
    sell_signals = df[df['sakata_signal'] == -1]
    
    if not buy_signals.empty:
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['low']*0.98, mode='markers',
                                marker=dict(symbol='triangle-up', size=14, color='green'), name='酒田買點'))
    if not sell_signals.empty:
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['high']*1.02, mode='markers',
                                marker=dict(symbol='triangle-down', size=14, color='red'), name='酒田賣點'))
    
    fig.update_layout(title=f"{target_symbol} K 線走勢與酒田戰法訊號", 
                      xaxis_rangeslider_visible=False, template='plotly_dark', height=600)
    st.plotly_chart(fig, use_container_width=True)
    
    # 指標儀表板
    st.markdown("### 📊 技術指標儀表板")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("RSI(14)", f"{latest['RSI_14']:.2f}", 
                delta="超買" if latest['RSI_14'] > 70 else "超賣" if latest['RSI_14'] < 30 else "中性")
    col2.metric("K 值", f"{latest['K']:.2f}")
    col3.metric("D 值", f"{latest['D']:.2f}")
    col4.metric("KD 黃金交叉", "✅ 是" if kd_golden else "❌ 否")
    
    # 酒田戰法說明
    with st.expander("📖 酒田戰法圖解說明"):
        st.markdown("""
        ### 酒田戰法基本型態
        1. **三陽 (Three White Soldiers)**: 連續三根陽線，收盤價逐日升高 → 強烈買進訊號
        2. **三陰 (Three Black Crows)**: 連續三根陰線，收盤價逐日降低 → 強烈賣出訊號
        3. **錘子 (Hammer)**: 下影線長、實體小 → 底部反轉買進訊號
        4. **上吊 (Hanging Man)**: 形似錘子但位於高檔 → 頂部反轉賣出訊號
        5. **十字星 (Doji)**: 開收盤接近 → 變盤訊號
        """)

# --- Tab 4: 策略回測 ---
with tab4:
    st.header(f"💰 {target_symbol} - 策略回測模擬")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ 回測參數設定")
    
    backtest_days = st.sidebar.slider("回測天數", 30, 200, 90)
    entry_condition = st.sidebar.selectbox("進場條件", ["MA20 之上 + KD 黃金交叉", "酒田買點訊號", "RSI < 30 超賣"])
    exit_condition = st.sidebar.selectbox("出場條件", ["MA20 之下 + KD 死亡交叉", "酒田賣點訊號", "RSI > 70 超買"])
    
    initial_capital = st.sidebar.number_input("初始資金 (元)", value=100000, step=10000)
    
    # 重新抓取指定天數的數據
    bt_df, _ = fetch_data(target_symbol, st.session_state.fubon_sdk, days=backtest_days)
    
    if bt_df is not None and not bt_df.empty:
        test_df = bt_df.copy()
        test_df['signal'] = 0
        
        # 根據選擇的條件產生訊號
        for i in range(1, len(test_df)):
            # 進場條件
            if entry_condition == "MA20 之上 + KD 黃金交叉":
                enter = test_df['close'].iloc[i] > test_df['SMA_20'].iloc[i] and \
                        test_df['K'].iloc[i-1] <= test_df['D'].iloc[i-1] and \
                        test_df['K'].iloc[i] > test_df['D'].iloc[i]
            elif entry_condition == "酒田買點訊號":
                enter = test_df['sakata_signal'].iloc[i] == 1
            else:  # RSI < 30
                enter = test_df['RSI_14'].iloc[i] < 30
            
            # 出場條件
            if exit_condition == "MA20 之下 + KD 死亡交叉":
                exit_sig = test_df['close'].iloc[i] < test_df['SMA_20'].iloc[i] and \
                           test_df['K'].iloc[i-1] >= test_df['D'].iloc[i-1] and \
                           test_df['K'].iloc[i] < test_df['D'].iloc[i]
            elif exit_condition == "酒田賣點訊號":
                exit_sig = test_df['sakata_signal'].iloc[i] == -1
            else:  # RSI > 70
                exit_sig = test_df['RSI_14'].iloc[i] > 70
            
            if enter:
                test_df.at[test_df.index[i], 'signal'] = 1
            elif exit_sig:
                test_df.at[test_df.index[i], 'signal'] = -1
        
        # 執行回測
        position = 0
        trades = []
        equity_curve = [initial_capital]
        
        for date, row in test_df.iterrows():
            if row['signal'] == 1 and position == 0:
                position = row['close']
                shares = initial_capital // position
                remaining_cash = initial_capital - shares * position
            elif row['signal'] == -1 and position != 0:
                profit = (row['close'] - position) * shares
                total_value = row['close'] * shares + remaining_cash
                equity_curve.append(total_value)
                trades.append(profit / initial_capital)
                position = 0
        
        # 計算績效
        win_rate = (len([t for t in trades if t > 0]) / len(trades) * 100) if trades else 0
        total_return = sum(trades) * 100 if trades else 0
        max_drawdown = 0
        peak = initial_capital
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_drawdown:
                max_drawdown = dd
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("總交易次數", f"{len(trades)} 次")
        col2.metric("勝率", f"{win_rate:.1f}%")
        col3.metric("累積報酬率", f"{total_return:.1f}%")
        col4.metric("最大回撤", f"{max_drawdown:.1f}%", delta_color="inverse")
        
        st.markdown("### 📈 資產增長曲線")
        st.line_chart(equity_curve)
        
        # 交易明細
        with st.expander("📋 查看交易明細"):
            trade_dates = test_df[test_df['signal'] != 0].index
            st.dataframe(test_df.loc[trade_dates, ['close', 'signal', 'pattern']].style.format({
                'close': '{:.2f}'
            }).applymap(lambda x: '🟢 買進' if x == 1 else ('🔴 賣出' if x == -1 else ''), subset=['signal']))
    else:
        st.warning("無法取得回測數據")
