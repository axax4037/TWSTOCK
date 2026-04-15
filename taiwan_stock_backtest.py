#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股股票機 - 命令行回測版本
功能包含：
1. 歷史 K 線抓取
2. 技術指標計算（SMA、RSI、KD）
3. 策略回測模擬
4. 操作建議生成
"""

import pandas as pd
from fubon_neo.sdk import FubonSDK
from datetime import datetime, timedelta

# ==========================================
# 核心設定（請替換為您的真實資訊）
# ==========================================
USER_ID = "您的身分證字號"
PASSWORD = "您的登入密碼"
CERT_PATH = r"D:\Users\MHChen\Desktop\您的身分證字號_20270414 富邦憑證.p12"
CERT_PASSWORD = "您的憑證密碼"

# ==========================================
# 技術指標計算函式
# ==========================================
def calculate_indicators_manual(df):
    """使用純 pandas 手動計算技術指標"""
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

# ==========================================
# 策略回測函式
# ==========================================
def run_backtest(df, symbol):
    """執行策略回測"""
    df = df.copy()
    df['signal'] = 0
    
    # 產生交易訊號
    for i in range(1, len(df)):
        # 買入訊號：收盤價 > 20MA 且 KD 黃金交叉
        if df['close'].iloc[i] > df['SMA_20'].iloc[i] and \
           (df['K'].iloc[i-1] < df['D'].iloc[i-1] and df['K'].iloc[i] > df['D'].iloc[i]):
            df.at[df.index[i], 'signal'] = 1
        # 賣出訊號：收盤價 < 20MA 或 KD 死亡交叉
        elif df['close'].iloc[i] < df['SMA_20'].iloc[i] or \
             (df['K'].iloc[i-1] > df['D'].iloc[i-1] and df['K'].iloc[i] < df['D'].iloc[i]):
            df.at[df.index[i], 'signal'] = -1

    # 模擬交易
    position, trades = 0, []
    for date, row in df.iterrows():
        if row['signal'] == 1 and position == 0:
            position = row['close']
        elif row['signal'] == -1 and position != 0:
            profit = (row['close'] - position) / position
            trades.append(profit)
            position = 0
            
    # 計算績效統計
    win_rate = (len([t for t in trades if t > 0]) / len(trades) * 100) if trades else 0
    total_return = sum(trades) * 100 if trades else 0
    
    print(f"\n📈 【策略回測報告 - {symbol}】")
    print(f"測試區間：{df.index[0].date()} ~ {df.index[-1].date()}")
    print(f"總交易次數：{len(trades)} 次 | 模擬勝率：{win_rate:.2f}% | 累積報酬：{total_return:.2f}%")
    
    return win_rate, total_return, len(trades)

# ==========================================
# 主程式
# ==========================================
def main():
    print("="*50)
    print("🎯 台股股票機 - 命令行回測系統")
    print("="*50)
    
    target_symbol = input("\n🔍 請輸入欲分析的股票代號 (預設 2330): ").strip() or "2330"
    
    # 初始化 SDK
    sdk = FubonSDK()
    res = sdk.login(USER_ID, PASSWORD, CERT_PATH, CERT_PASSWORD)
    
    if not res.is_success:
        print("❌ 登入失敗:", res.message)
        return

    # 啟動行情模組
    sdk.init_realtime()
    print(f"\n✅ 登入成功！正在抓取 {target_symbol} 歷史 K 線...")
    
    # 設定時間範圍
    now = datetime.now()
    start_date = (now - timedelta(days=200)).strftime('%Y-%m-%d')
    end_date = now.strftime('%Y-%m-%d')
    
    try:
        # 呼叫 candles API
        kline_res = sdk.marketdata.rest_client.stock.historical.candles(**{
            "symbol": target_symbol,
            "from": start_date,
            "to": end_date,
            "fields": "open,high,low,close,volume"
        })
        
        if kline_res and 'data' in kline_res and len(kline_res['data']) > 0:
            df = pd.DataFrame(kline_res['data'])
            
            # 處理日期欄位
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            elif 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df.rename(columns={'time': 'date'}, inplace=True)
            
            df.set_index('date', inplace=True)
            df = df.sort_index()
            
            # 計算技術指標
            df = calculate_indicators_manual(df)
            today = df.iloc[-1]
            
            # 顯示當前數據
            print(f"\n📊 數據最後日期：{df.index[-1].date()}")
            print(f"   收盤價：{today['close']}")
            print(f"   20MA: {today['SMA_20']:.2f}")
            print(f"   RSI: {rsi:.2f}" if (rsi := today.get('RSI_14')) is not None else "")
            print(f"   K: {today['K']:.2f}, D: {today['D']:.2f}")
            
            # 判斷趨勢與操作建議
            is_uptrend = today['close'] > today['SMA_20']
            rsi = today.get('RSI_14', 50)
            
            print("\n💡 明日操作建議:")
            if is_uptrend and rsi > 50:
                print("   🟢 強勢偏多 (建議買進/持有)")
            elif not is_uptrend and rsi < 50:
                print("   🔴 弱勢偏空 (建議賣出/觀望)")
            else:
                print("   ⚪ 震盪整理 (建議觀望)")
            
            # 執行回測
            run_backtest(df, target_symbol)
        else:
            print(f"⚠️ 無法取得資料，可能尚未開盤或代號錯誤。")
            
    except Exception as e:
        print(f"❌ 執行錯誤：{e}")
    finally:
        sdk.logout()
        print("\n👋 已斷線，感謝使用！")

if __name__ == "__main__":
    main()
