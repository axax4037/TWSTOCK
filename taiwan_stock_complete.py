#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股全方位戰情室 - 完整功能版
功能清單：
1. 即時成交量監控
2. 即時大單偵測
3. 大戶動向分析
4. 成交量預測
5. 漲跌停預測
6. 盤後資料（收盤價、成交量）
7. 偏多偏空操作建議
8. 策略回測模擬
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from fubon_neo.sdk import FubonSDK
from datetime import datetime, timedelta
import numpy as np
import json
import time
from collections import deque

# ==========================================
# 1. 頁面基本設定與狀態初始化
# ==========================================
st.set_page_config(page_title="台股全方位戰情室", layout="wide", page_icon="📈")

if 'fubon_sdk' not in st.session_state:
    st.session_state.fubon_sdk = None
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False
if 'realtime_data' not in st.session_state:
    st.session_state.realtime_data = []
if 'large_orders' not in st.session_state:
    st.session_state.large_orders = []
if 'big_player_flow' not in st.session_state:
    st.session_state.big_player_flow = {'buy': 0, 'sell': 0, 'net': 0}
if 'stock_name_cache' not in st.session_state:
    st.session_state.stock_name_cache = {}

# ==========================================
# 2. 輔助函式：股票名稱查詢
# ==========================================
@st.cache_data(ttl=3600)  # 快取 1 小時
def get_stock_name(symbol, sdk):
    """查詢股票名稱"""
    try:
        # 使用 securities API 查詢標的基本資訊
        res = sdk.marketdata.rest_client.stock.securities.get(params={'symbol': symbol})
        if res and 'data' in res and len(res['data']) > 0:
            return res['data'][0].get('name', '未知名稱')
        return '未知名稱'
    except Exception as e:
        return '查詢失敗'

# ==========================================
# 2. 核心計算函式
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
    
    # 4. 成交量移動平均
    df['VOL_MA5'] = df['volume'].rolling(window=5).mean()
    df['VOL_MA10'] = df['volume'].rolling(window=10).mean()
    
    # 5. 價格變化率
    df['PRICE_CHANGE'] = df['close'].pct_change() * 100
    
    return df.dropna()

def predict_volume(df):
    """成交量預測：使用簡單線性回歸預測明日成交量"""
    if len(df) < 20:
        return None
    
    recent_vol = df['volume'].tail(10).values
    days = np.arange(len(recent_vol))
    
    # 簡單線性回歸
    slope = np.polyfit(days, recent_vol, 1)[0]
    predicted_vol = recent_vol[-1] + slope
    
    # 確保預測值為正
    predicted_vol = max(predicted_vol, recent_vol.mean() * 0.8)
    
    return int(predicted_vol)

def predict_price_limit(df):
    """漲跌停預測：基於技術指標與波動率"""
    if len(df) < 20:
        return None, None, None
    
    latest = df.iloc[-1]
    
    # 計算波動率
    returns = df['close'].pct_change().dropna()
    volatility = returns.std()
    
    # 計算動能
    momentum = (latest['close'] - df['close'].iloc[-10]) / df['close'].iloc[-10]
    
    # RSI 極值判斷
    rsi = latest.get('RSI_14', 50)
    
    # 漲停機率（簡化模型）
    up_prob = 0.5
    if momentum > 0.05:  # 強勢動能
        up_prob += 0.2
    if rsi > 70:  # 超買但可能繼續衝
        up_prob += 0.15
    if latest['close'] > latest.get('SMA_20', latest['close'] * 1.05):
        up_prob += 0.1
    if volatility > 0.03:  # 高波動
        up_prob += 0.1
    
    # 跌停機率
    down_prob = 0.5
    if momentum < -0.05:
        down_prob += 0.2
    if rsi < 30:
        down_prob += 0.15
    if latest['close'] < latest.get('SMA_20', latest['close'] * 0.95):
        down_prob += 0.1
    if volatility > 0.03:
        down_prob += 0.1
    
    # 歸一化
    total = up_prob + down_prob
    up_prob = min(up_prob / total * 100, 85)  # 上限 85%
    down_prob = min(down_prob / total * 100, 85)
    
    # 預估價格區間
    current_price = latest['close']
    limit_up = current_price * 1.1  # 台股漲停 10%
    limit_down = current_price * 0.9  # 台股跌停 10%
    
    return up_prob, down_prob, (limit_up, limit_down)

def analyze_big_player(df, realtime_trades=None):
    """大戶動向分析"""
    if realtime_trades and len(realtime_trades) > 0:
        # 使用即時交易資料
        large_buy = sum(t['volume'] for t in realtime_trades if t.get('side', 'buy') == 'buy' and t['volume'] >= 50)
        large_sell = sum(t['volume'] for t in realtime_trades if t.get('side', 'sell') == 'sell' and t['volume'] >= 50)
        net_flow = large_buy - large_sell
        
        return {
            'buy': large_buy,
            'sell': large_sell,
            'net': net_flow,
            'status': '進場' if net_flow > 0 else '出場' if net_flow < 0 else '觀望'
        }
    
    # 使用歷史資料估算
    if len(df) < 5:
        return {'buy': 0, 'sell': 0, 'net': 0, 'status': '資料不足'}
    
    recent = df.tail(5)
    avg_vol = recent['volume'].mean()
    
    # 簡化估算：假設大於平均成交量 2 倍為大戶進出
    estimated_buy = recent[recent['volume'] > avg_vol * 1.5]['volume'].sum() * 0.3
    estimated_sell = recent[recent['volume'] > avg_vol * 1.5]['volume'].sum() * 0.2
    net_flow = estimated_buy - estimated_sell
    
    return {
        'buy': int(estimated_buy),
        'sell': int(estimated_sell),
        'net': int(net_flow),
        'status': '小幅進場' if net_flow > 0 else '小幅出場' if net_flow < 0 else '觀望'
    }

def generate_trading_signal(df):
    """產生偏多偏空操作建議"""
    if len(df) < 20:
        return "資料不足", "off"
    
    latest = df.iloc[-1]
    
    is_uptrend = latest['close'] > latest.get('SMA_20', latest['close'])
    rsi = latest.get('RSI_14', 50)
    k_val = latest.get('K', 50)
    d_val = latest.get('D', 50)
    
    # 多頭條件
    bullish_score = 0
    if is_uptrend:
        bullish_score += 2
    if rsi > 50 and rsi < 70:
        bullish_score += 2
    if k_val > d_val:
        bullish_score += 1
    if latest['close'] > df['open'].iloc[-1]:
        bullish_score += 1
    
    # 空頭條件
    bearish_score = 0
    if not is_uptrend:
        bearish_score += 2
    if rsi < 50 and rsi > 30:
        bearish_score += 2
    if k_val < d_val:
        bearish_score += 1
    if latest['close'] < df['open'].iloc[-1]:
        bearish_score += 1
    
    # 判斷訊號
    if bullish_score >= 5:
        return "🟢 強勢偏多 - 建議買進/持有", "normal"
    elif bullish_score >= 3:
        return "🟡 溫和偏多 - 可逢低佈局", "normal"
    elif bearish_score >= 5:
        return "🔴 弱勢偏空 - 建議賣出/觀望", "inverse"
    elif bearish_score >= 3:
        return "🟠 溫和偏空 - 宜減碼", "inverse"
    else:
        return "⚪ 震盪整理 - 建議觀望", "off"

def run_backtest(df):
    """策略回測模擬"""
    test_df = df.copy()
    test_df['signal'] = 0
    
    # 產生交易訊號
    for i in range(1, len(test_df)):
        # 買入條件：價格在均線上 + KD 黃金交叉
        if (test_df['close'].iloc[i] > test_df['SMA_20'].iloc[i] and 
            test_df['K'].iloc[i-1] < test_df['D'].iloc[i-1] and 
            test_df['K'].iloc[i] > test_df['D'].iloc[i]):
            test_df.at[test_df.index[i], 'signal'] = 1
        # 賣出條件：價格在均線下 或 KD 死亡交叉
        elif (test_df['close'].iloc[i] < test_df['SMA_20'].iloc[i] or 
              (test_df['K'].iloc[i-1] > test_df['D'].iloc[i-1] and 
               test_df['K'].iloc[i] < test_df['D'].iloc[i])):
            test_df.at[test_df.index[i], 'signal'] = -1

    # 模擬交易
    position = 0
    profits = []
    equity_curve = [100000]
    trades = []
    
    for date, row in test_df.iterrows():
        if row['signal'] == 1 and position == 0:
            position = row['close']
            trades.append({'date': date, 'type': 'buy', 'price': row['close']})
        elif row['signal'] == -1 and position != 0:
            profit = (row['close'] - position) / position
            profits.append(profit)
            equity_curve.append(equity_curve[-1] * (1 + profit))
            trades.append({'date': date, 'type': 'sell', 'price': row['close'], 'profit': profit})
            position = 0
    
    # 計算績效指標
    win_rate = (len([p for p in profits if p > 0]) / len(profits) * 100) if profits else 0
    total_return = (equity_curve[-1] - 100000) / 1000 if equity_curve else 0
    avg_profit = np.mean(profits) if profits else 0
    max_drawdown = min(equity_curve) / max(equity_curve) - 1 if equity_curve else 0
    
    return {
        'trades': len(profits),
        'win_rate': win_rate,
        'total_return': total_return,
        'avg_profit': avg_profit,
        'max_drawdown': max_drawdown,
        'equity_curve': equity_curve,
        'trade_details': trades
    }

@st.cache_data(ttl=60)
def fetch_and_analyze_data(symbol, _sdk):
    """抓取並分析歷史數據"""
    now = datetime.now()
    start_date = (now - timedelta(days=200)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        kline_res = _sdk.marketdata.rest_client.stock.historical.candles(**{
            "symbol": symbol,
            "from": start_date,
            "to": end_date,
            "fields": "open,high,low,close,volume"
        })
        
        if not kline_res or 'data' not in kline_res or len(kline_res['data']) == 0:
            return None
            
        df = pd.DataFrame(kline_res['data'])
        
        # 處理日期欄位
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
        elif 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)

        df = df.sort_index()
        df = calculate_indicators_manual(df)
        
        return df
        
    except Exception as e:
        st.error(f"抓取數據失敗：{e}")
        return None

def plot_candlestick_with_indicators(df, title):
    """繪製 K 線圖與技術指標"""
    fig = go.Figure()
    
    # K 線
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='K 線',
        increasing_line_color='red',
        decreasing_line_color='green'
    ))
    
    # SMA 20
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['SMA_20'],
        line=dict(color='#FFA500', width=2),
        name='20MA'
    ))
    
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        template='plotly_dark',
        height=500
    )
    
    return fig

def plot_volume_chart(df):
    """繪製成交量圖"""
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['volume'],
        name='成交量',
        marker_color=np.where(df['close'] >= df['open'], 'red', 'green')
    ))
    
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['VOL_MA5'],
        line=dict(color='blue', width=2),
        name='VOL MA5'
    ))
    
    fig.update_layout(
        title='成交量走勢',
        xaxis_rangeslider_visible=False,
        template='plotly_dark',
        height=300
    )
    
    return fig

# ==========================================
# 3. 側邊欄設定
# ==========================================
st.sidebar.title("⚙️ 系統設定與連線")
st.sidebar.markdown("---")

user_id = st.sidebar.text_input("身分證字號", type="password", key="user_id")
password = st.sidebar.text_input("登入密碼", type="password", key="pwd")
cert_path = st.sidebar.text_input("憑證路徑", value=r"D:\Users\MHChen\Desktop\您的身分證字號_20270414富邦憑證.p12")
cert_password = st.sidebar.text_input("憑證密碼", type="password", key="cert_pwd")

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
            else:
                st.sidebar.error(f"❌ 登入失敗：{res.message}")
        except Exception as e:
            st.sidebar.error(f"連線發生錯誤：{e}")

st.sidebar.markdown("---")
st.sidebar.title("🎯 標的選擇與監控")
target_symbol = st.sidebar.text_input("請輸入台股代碼 (例如：2317, 2881)", value="2330")

# 查詢並顯示股票名稱
stock_name = "..."
if st.session_state.is_logged_in and target_symbol:
    stock_name = get_stock_name(target_symbol, st.session_state.fubon_sdk)
    if stock_name not in ["...", "未知名稱", "查詢失敗"]:
        st.sidebar.info(f"🏷️ **{target_symbol} {stock_name}**")
    else:
        st.sidebar.warning(f"⚠️ 無法查詢 {target_symbol} 的股票名稱")
elif not st.session_state.is_logged_in:
    st.sidebar.warning("請先連線 API 以查詢股票名稱")

large_order_threshold = st.sidebar.number_input("🚨 大單門檻 (張)", value=50, min_value=1)

# ==========================================
# 4. 主畫面
# ==========================================
display_title = f"{target_symbol} {stock_name}" if stock_name not in ["...", "未知名稱", "查詢失敗"] else f"{target_symbol}"
st.title(f"📊 台股全方位戰情室：{display_title}")
st.markdown("**功能清單：** 即時成交量 | 即時大單 | 大戶動向 | 成交量預測 | 漲跌停預測 | 盤後資料 | 操作建議 | 策略回測")

if not st.session_state.is_logged_in:
    st.warning("⚠️ 請先由左側面板輸入憑證資訊並連線 API。")
    st.stop()

with st.spinner(f"正在載入 {target_symbol} 數據..."):
    df = fetch_and_analyze_data(target_symbol, st.session_state.fubon_sdk)

if df is None or df.empty:
    st.error("無法取得數據，請確認代號正確或稍後再試。")
    st.stop()

latest = df.iloc[-1]
prev_close = df['close'].iloc[-2] if len(df) > 1 else latest['close']
price_change = ((latest['close'] - prev_close) / prev_close * 100) if prev_close else 0

# ==========================================
# 分頁式佈局
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚡ 即時戰情",
    "📈 技術分析",
    "🔮 預測中心",
    "💰 策略回測",
    "📋 盤後資料"
])

# --- Tab 1: 即時戰情 ---
with tab1:
    st.header(f"🔥 {display_title} 即時戰情")
    
    # 第一列：關鍵指標
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="最新價",
            value=f"{latest['close']:.2f}",
            delta=f"{price_change:.2f}%"
        )
    
    with col2:
        pred_vol = predict_volume(df)
        st.metric(
            label="即時成交量",
            value=f"{int(latest['volume']):,} 張",
            delta=f"預估全日：{int(pred_vol):,} 張" if pred_vol else "N/A"
        )
    
    with col3:
        big_player = analyze_big_player(df)
        st.metric(
            label="大戶淨進出",
            value=f"{big_player['net']:+,} 張",
            delta=big_player['status']
        )
    
    with col4:
        limit_up_pct = ((latest['close'] * 1.1 - latest['close']) / latest['close'] * 100)
        st.metric(
            label="距漲停空間",
            value=f"{limit_up_pct:.1f}%",
            delta=f"漲停價：{latest['close']*1.1:.2f}"
        )
    
    # 第二列：大單監控
    st.markdown("---")
    st.subheader(f"🚨 即時大單監控 (>{large_order_threshold} 張)")
    
    # 模擬大單資料（實際應用需連接 WebSocket）
    if st.session_state.large_orders:
        for order in st.session_state.large_orders[-10:]:
            color = "🔴" if order.get('side') == 'sell' else "🟢"
            st.markdown(f"{color} {order.get('time', 'N/A')} | 價格：{order.get('price', 0):.2f} | 張數：{order.get('volume', 0):,} 張")
    else:
        st.info("等待即時交易資料流入...（需連接 WebSocket）")
    
    # 第三列：成交量走勢
    st.plotly_chart(plot_volume_chart(df), use_container_width=True)

# --- Tab 2: 技術分析 ---
with tab2:
    st.header(f"📈 {display_title} 技術分析")
    
    # 操作建議
    signal, color = generate_trading_signal(df)
    st.metric("💡 操作建議", signal, delta_color=color)
    
    # K 線圖
    st.plotly_chart(plot_candlestick_with_indicators(df, f"{target_symbol} K 線走勢"), use_container_width=True)
    
    # 技術指標詳情
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 均線系統")
        st.write(f"**20MA:** {latest.get('SMA_20', 'N/A'):.2f}" if pd.notna(latest.get('SMA_20')) else "**20MA:** N/A")
        st.write(f"**價位關係:** {'站上' if latest['close'] > latest.get('SMA_20', 0) else '站下'} 20MA")
    
    with col2:
        st.markdown("### 📊 RSI 指標")
        rsi_val = latest.get('RSI_14', 50)
        st.write(f"**RSI(14):** {rsi_val:.2f}")
        if rsi_val > 70:
            st.write("🔴 超買區")
        elif rsi_val < 30:
            st.write("🟢 超賣區")
        else:
            st.write("⚪ 中性區")
    
    with col3:
        st.markdown("### 📊 KD 指標")
        k_val = latest.get('K', 50)
        d_val = latest.get('D', 50)
        st.write(f"**K:** {k_val:.2f}")
        st.write(f"**D:** {d_val:.2f}")
        if k_val > d_val:
            st.write("🟢 黃金交叉")
        else:
            st.write("🔴 死亡交叉")

# --- Tab 3: 預測中心 ---
with tab3:
    st.header(f"🔮 {display_title} 預測中心")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 成交量預測")
        pred_vol = predict_volume(df)
        if pred_vol:
            st.metric(
                label="預估明日成交量",
                value=f"{int(pred_vol):,} 張",
                delta=f"較今日：{((pred_vol - latest['volume']) / latest['volume'] * 100):+.1f}%"
            )
            
            # 成交量趨勢圖
            vol_fig = go.Figure()
            vol_fig.add_trace(go.Scatter(
                x=df.index[-20:],
                y=df['volume'].tail(20),
                mode='lines+markers',
                name='實際成交量'
            ))
            vol_fig.add_trace(go.Scatter(
                x=[df.index[-1] + timedelta(days=1)],
                y=[pred_vol],
                mode='markers',
                marker=dict(size=15, color='red'),
                name='預測值'
            ))
            vol_fig.update_layout(
                title='成交量預測趨勢',
                template='plotly_dark',
                height=300
            )
            st.plotly_chart(vol_fig, use_container_width=True)
        else:
            st.warning("資料不足，無法預測")
    
    with col2:
        st.subheader("🎯 漲跌停預測")
        up_prob, down_prob, limits = predict_price_limit(df)
        
        if up_prob and down_prob:
            st.metric(
                label="漲停機率",
                value=f"{up_prob:.1f}%",
                delta=f"漲停價：{limits[0]:.2f}"
            )
            st.metric(
                label="跌停機率",
                value=f"{down_prob:.1f}%",
                delta=f"跌停價：{limits[1]:.2f}"
            )
            
            # 機率條
            prob_df = pd.DataFrame({
                '情境': ['漲停', '跌停', '其他'],
                '機率': [up_prob, down_prob, 100 - up_prob - down_prob]
            })
            prob_fig = px.bar(prob_df, x='情境', y='機率', color='機率', 
                             color_continuous_scale='RdYlGn', title='漲跌停機率分布')
            prob_fig.update_layout(template='plotly_dark', height=300)
            st.plotly_chart(prob_fig, use_container_width=True)
        else:
            st.warning("資料不足，無法預測")
    
    # 大戶動向詳細分析
    st.markdown("---")
    st.subheader("🐋 大戶動向深度分析")
    
    big_player = analyze_big_player(df)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("大戶買進量", f"{big_player['buy']:,} 張")
    col2.metric("大戶賣出量", f"{big_player['sell']:,} 張")
    col3.metric("淨進出", f"{big_player['net']:+,} 張", delta=big_player['status'])
    
    # 大戶動向圖
    flow_fig = go.Figure()
    flow_fig.add_trace(go.Bar(
        x=['買進', '賣出', '淨進出'],
        y=[big_player['buy'], big_player['sell'], big_player['net']],
        marker_color=['red', 'green', 'blue' if big_player['net'] > 0 else 'gray']
    ))
    flow_fig.update_layout(
        title='大戶進出分布',
        template='plotly_dark',
        height=300
    )
    st.plotly_chart(flow_fig, use_container_width=True)

# --- Tab 4: 策略回測 ---
with tab4:
    st.header(f"💰 {display_title} 策略回測模擬")
    
    st.markdown("""
    **策略說明：**
    - **買入訊號：** 價格站上 20MA + KD 黃金交叉
    - **賣出訊號：** 價格跌破 20MA 或 KD 死亡交叉
    - **初始資金：** 100,000 元
    """)
    
    backtest_result = run_backtest(df)
    
    # 績效指標
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("總交易次數", f"{backtest_result['trades']} 次")
    col2.metric("勝率", f"{backtest_result['win_rate']:.1f}%")
    col3.metric("累積報酬率", f"{backtest_result['total_return']:.1f}%")
    col4.metric("最大回撤", f"{backtest_result['max_drawdown']*100:.1f}%")
    
    # 資產曲線
    if len(backtest_result['equity_curve']) > 1:
        equity_fig = go.Figure()
        equity_fig.add_trace(go.Scatter(
            y=backtest_result['equity_curve'],
            mode='lines',
            fill='tozeroy',
            name='資產淨值'
        ))
        equity_fig.update_layout(
            title='資產增長曲線',
            xaxis_title='交易次數',
            yaxis_title='資產淨值 (元)',
            template='plotly_dark',
            height=400
        )
        st.plotly_chart(equity_fig, use_container_width=True)
    
    # 交易明細
    if backtest_result['trade_details']:
        with st.expander("📋 查看交易明細"):
            trade_df = pd.DataFrame(backtest_result['trade_details'])
            if 'profit' in trade_df.columns:
                trade_df['profit'] = trade_df['profit'].apply(lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A")
            st.dataframe(trade_df, use_container_width=True)

# --- Tab 5: 盤後資料 ---
with tab5:
    st.header(f"📋 {display_title} 盤後資料")
    
    # 今日重點數據
    st.subheader("📊 今日重點數據")
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric("收盤價", f"{latest['close']:.2f} 元", delta=f"{price_change:+.2f}%")
    col2.metric("成交量", f"{int(latest['volume']):,} 張")
    col3.metric("成交金額", f"{int(latest['close'] * latest['volume'] / 1000):,} 千元")
    
    # OHLC 詳細資料
    st.subheader("📈 今日 OHLC 資料")
    
    ohlc_col1, ohlc_col2 = st.columns(2)
    
    with ohlc_col1:
        st.markdown(f"""
        - **開盤價：** {latest['open']:.2f} 元
        - **最高價：** {latest['high']:.2f} 元
        - **最低價：** {latest['low']:.2f} 元
        - **收盤價：** {latest['close']:.2f} 元
        """)
    
    with ohlc_col2:
        today_range = latest['high'] - latest['low']
        st.markdown(f"""
        - **漲跌幅：** {price_change:+.2f}%
        - **振幅：** {today_range/prev_close*100:.2f}%
        - **昨收：** {prev_close:.2f} 元
        - **今開 vs 昨收：** {((latest['open'] - prev_close) / prev_close * 100):+.2f}%
        """)
    
    # 近期走勢表
    st.subheader("📅 近期走勢表")
    
    recent_df = df.tail(10)[['open', 'high', 'low', 'close', 'volume']].copy()
    recent_df['漲跌%'] = recent_df['close'].pct_change() * 100
    recent_df = recent_df.round(2)
    
    st.dataframe(recent_df.style.format({
        'open': '{:.2f}',
        'high': '{:.2f}',
        'low': '{:.2f}',
        'close': '{:.2f}',
        'volume': '{:,.0f}',
        '漲跌%': '{:+.2f}%'
    }), use_container_width=True)
    
    # 匯出按鈕
    csv_data = df.to_csv()
    st.download_button(
        label="📥 下載完整歷史數據 (CSV)",
        data=csv_data,
        file_name=f"{target_symbol}_historical_data.csv",
        mime="text/csv"
    )

# ==========================================
# 頁尾
# ==========================================
st.markdown("---")
st.caption("⚠️ 本系統僅供參考，不構成投資建議。投資有風險，入市須謹慎。")
st.caption(f"最後更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
