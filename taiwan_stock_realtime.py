#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股即時大單監控 - WebSocket 版本
功能包含：
1. 即時成交資料監聽
2. 大單警示通知
3. 自訂門檻設定
"""

import json
import time
from datetime import datetime
from fubon_neo.sdk import FubonSDK

# ==========================================
# 核心設定（請替換為您的真實資訊）
# ==========================================
USER_ID = "您的身分證字號"
PASSWORD = "您的登入密碼"
CERT_PATH = r"D:\Users\MHChen\Desktop\您的身分證字號_20270414 富邦憑證.p12"
CERT_PASSWORD = "您的憑證密碼"

# 預設大單門檻（張）
LARGE_ORDER_THRESHOLD = 50

# ==========================================
# WebSocket 回調函式
# ==========================================
def on_message(message):
    """處理 WebSocket 訊息"""
    data = json.loads(message)
    
    # 只處理交易資料
    if data.get('event') == 'data' and data.get('channel') == 'trades':
        c = data.get('content', {})
        price = c.get('price')
        vol = c.get('volume')
        symbol = c.get('symbol')
        
        # 大單判定
        if vol >= LARGE_ORDER_THRESHOLD:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"\n🔥 [{timestamp}] 【大單警示】")
            print(f"   股票代號：{symbol}")
            print(f"   成交價格：{price}")
            print(f"   成交量：{vol} 張")
            print("-" * 40)

def on_connect():
    """連線成功回調"""
    print("\n✅ WebSocket 連線成功！")
    print(f"📡 開始監控 {target_symbol} (門檻：{LARGE_ORDER_THRESHOLD} 張)")
    print("按下 Ctrl+C 可停止監控\n" + "-"*40)

def on_disconnect():
    """斷線回調"""
    print("\n⚠️ WebSocket 已斷線")

# ==========================================
# 主程式
# ==========================================
def main():
    global LARGE_ORDER_THRESHOLD, target_symbol
    
    print("="*50)
    print("🎯 台股即時大單監控系統")
    print("="*50)
    
    # 取得使用者輸入
    target_symbol = input("\n🔍 請輸入欲即時監控的股票代號 (預設 2330): ").strip() or "2330"
    threshold_input = input("🚨 請設定大單警示門檻張數 (預設 50): ").strip() or "50"
    LARGE_ORDER_THRESHOLD = int(threshold_input)
    
    # 初始化 SDK
    sdk = FubonSDK()
    res = sdk.login(USER_ID, PASSWORD, CERT_PATH, CERT_PASSWORD)
    
    if not res.is_success:
        print("❌ 登入失敗:", res.message)
        return
        
    # 啟動即時行情模組
    sdk.init_realtime()
    
    # 取得 WebSocket 客戶端
    stock_client = sdk.marketdata.websocket_client.stock
    
    # 註冊回調函式
    stock_client.on("message", on_message)
    stock_client.on("connect", on_connect)
    stock_client.on("disconnect", on_disconnect)
    
    # 連線並訂閱
    stock_client.connect()
    stock_client.subscribe({'channel': 'trades', 'symbol': target_symbol})
    
    try:
        # 持續監聽
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 收到停止指令")
        stock_client.unsubscribe({'channel': 'trades', 'symbol': target_symbol})
        stock_client.disconnect()
        sdk.logout()
        print("👋 系統已安全斷線，感謝使用！")

if __name__ == "__main__":
    main()
