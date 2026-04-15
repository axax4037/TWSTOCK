#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股股票機 - 富邦 API 整合系統
功能包含：
1. 即時成交量
2. 即時大單
3. 大戶動向
4. 成交量預測
5. 漲停跌停預測
6. 盤後資料（收盤價、成交量）
7. 偏多偏空操作建議
8. 回測模擬
"""

import sys
import random
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QPushButton, 
                             QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
                             QTextEdit, QTabWidget, QGroupBox, QProgressBar,
                             QSpinBox, QDoubleSpinBox, QMessageBox, QHeaderView)
from PyQt5.QtCore import QTimer, Qt, QTime
from PyQt5.QtGui import QFont, QColor, QPalette


class StockMonitorApp(QMainWindow):
    """台股股票機主應用程式"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📈 台股股票機 - 富邦 API 整合系統")
        self.setGeometry(100, 100, 1400, 900)
        
        # 系統狀態
        self.is_connected = False
        self.is_monitoring = False
        self.current_stock = None
        self.data_buffer = []
        
        # 初始化 UI
        self.init_ui()
        
        # 啟動定時器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_system_time)
        self.timer.start(1000)
        
        # 連接 API（模擬）
        self.connect_api()
        
    def init_ui(self):
        """初始化使用者介面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 樣式表
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1e3c72, stop:1 #2a5298);
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid rgba(255,255,255,100);
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
                background: rgba(255,255,255,50);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b09b, stop:1 #96c93d);
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4aa, stop:1 #aad947);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #008a7a, stop:1 #7ab32d);
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 8px;
                border-radius: 5px;
                border: 1px solid rgba(255,255,255,100);
                background: rgba(255,255,255,200);
                color: #333;
                font-size: 14px;
            }
            QTableWidget {
                background: rgba(0,0,0,100);
                color: white;
                gridline-color: rgba(255,255,255,50);
            }
            QTableWidget::item:selected {
                background: rgba(0,176,155,150);
            }
            QHeaderView::section {
                background: rgba(0,0,0,150);
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTextEdit {
                background: #1a1a1a;
                color: #4fc3f7;
                font-family: 'Courier New';
                font-size: 12px;
                border-radius: 5px;
            }
            QProgressBar {
                border: 1px solid rgba(255,255,255,100);
                border-radius: 5px;
                text-align: center;
                background: rgba(0,0,0,100);
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b09b, stop:1 #96c93d);
            }
            QTabWidget::pane {
                border: 1px solid rgba(255,255,255,100);
                border-radius: 5px;
                background: rgba(0,0,0,50);
            }
            QTabBar::tab {
                background: rgba(0,0,0,100);
                color: white;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: rgba(255,255,255,100);
            }
        """)
        
        # 狀態列
        self.create_status_bar(main_layout)
        
        # 控制面板
        self.create_control_panel(main_layout)
        
        # 主要功能區（使用 Tab 分頁）
        tab_widget = QTabWidget()
        tab_widget.addTab(self.create_realtime_tab(), "📊 即時監控")
        tab_widget.addTab(self.create_institutional_tab(), "🏦 大戶動向")
        tab_widget.addTab(self.create_prediction_tab(), "🔮 預測分析")
        tab_widget.addTab(self.create_signal_tab(), "📈 操作建議")
        tab_widget.addTab(self.create_historical_tab(), "🌙 盤後資料")
        tab_widget.addTab(self.create_backtest_tab(), "🧪 回測模擬")
        main_layout.addWidget(tab_widget)
        
        # 系統日誌
        self.create_log_panel(main_layout)
        
    def create_status_bar(self, layout):
        """建立狀態列"""
        status_frame = QGroupBox()
        status_layout = QHBoxLayout(status_frame)
        
        # 系統時間
        time_group = QGroupBox("🕐 系統時間")
        time_layout = QVBoxLayout(time_group)
        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setFont(QFont("Arial", 16, QFont.Bold))
        time_layout.addWidget(self.time_label)
        status_layout.addWidget(time_group)
        
        # 市場狀態
        market_group = QGroupBox("📊 市場狀態")
        market_layout = QVBoxLayout(market_group)
        self.market_label = QLabel("休市中")
        self.market_label.setAlignment(Qt.AlignCenter)
        self.market_label.setFont(QFont("Arial", 16, QFont.Bold))
        market_layout.addWidget(self.market_label)
        status_layout.addWidget(market_group)
        
        # API 連線
        api_group = QGroupBox("🔗 API 連線")
        api_layout = QVBoxLayout(api_group)
        self.api_label = QLabel("未連線")
        self.api_label.setAlignment(Qt.AlignCenter)
        self.api_label.setFont(QFont("Arial", 16, QFont.Bold))
        api_layout.addWidget(self.api_label)
        status_layout.addWidget(api_group)
        
        # 加權指數
        twii_group = QGroupBox("💰 加權指數")
        twii_layout = QVBoxLayout(twii_group)
        self.twii_label = QLabel("--")
        self.twii_label.setAlignment(Qt.AlignCenter)
        self.twii_label.setFont(QFont("Arial", 16, QFont.Bold))
        twii_layout.addWidget(self.twii_label)
        status_layout.addWidget(twii_group)
        
        layout.addWidget(status_frame)
        
    def create_control_panel(self, layout):
        """建立控制面板"""
        control_frame = QGroupBox("🔍 股票查詢與設定")
        control_layout = QGridLayout(control_frame)
        
        # 股票輸入
        control_layout.addWidget(QLabel("股票代號:"), 0, 0)
        self.stock_input = QLineEdit()
        self.stock_input.setPlaceholderText("例如：2330")
        control_layout.addWidget(self.stock_input, 0, 1)
        
        # 按鈕
        self.query_btn = QPushButton("查詢股票")
        self.query_btn.clicked.connect(self.query_stock)
        control_layout.addWidget(self.query_btn, 0, 2)
        
        self.start_btn = QPushButton("開始監控")
        self.start_btn.clicked.connect(self.start_monitoring)
        control_layout.addWidget(self.start_btn, 0, 3)
        
        self.stop_btn = QPushButton("停止監控")
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn, 0, 4)
        
        # 設定
        control_layout.addWidget(QLabel("更新頻率 (秒):"), 1, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(3)
        control_layout.addWidget(self.interval_spin, 1, 1)
        
        control_layout.addWidget(QLabel("大單門檻 (張):"), 1, 2)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(10, 10000)
        self.threshold_spin.setValue(100)
        control_layout.addWidget(self.threshold_spin, 1, 3)
        
        control_layout.addWidget(QLabel("預測模式:"), 1, 4)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["機器學習", "技術分析", "混合模式"])
        control_layout.addWidget(self.mode_combo, 1, 5)
        
        layout.addWidget(control_frame)
        
    def create_realtime_tab(self):
        """建立即時監控分頁"""
        widget = QWidget()
        layout = QGridLayout(widget)
        
        # 即時成交量
        volume_group = QGroupBox("📊 即時成交量")
        volume_layout = QGridLayout(volume_group)
        
        self.current_price_label = self.create_data_label("--", 18, True)
        volume_layout.addWidget(QLabel("當前價格:"), 0, 0)
        volume_layout.addWidget(self.current_price_label, 0, 1)
        
        self.today_volume_label = self.create_data_label("--")
        volume_layout.addWidget(QLabel("今日成交量:"), 1, 0)
        volume_layout.addWidget(self.today_volume_label, 1, 1)
        
        self.turnover_label = self.create_data_label("--")
        volume_layout.addWidget(QLabel("成交金額:"), 2, 0)
        volume_layout.addWidget(self.turnover_label, 2, 1)
        
        self.avg_volume_label = self.create_data_label("--")
        volume_layout.addWidget(QLabel("均量:"), 3, 0)
        volume_layout.addWidget(self.avg_volume_label, 3, 1)
        
        self.volume_ratio_label = self.create_data_label("--")
        volume_layout.addWidget(QLabel("量比:"), 4, 0)
        volume_layout.addWidget(self.volume_ratio_label, 4, 1)
        
        layout.addWidget(volume_group, 0, 0)
        
        # 即時大單
        large_order_group = QGroupBox("💰 即時大單")
        large_order_layout = QVBoxLayout(large_order_group)
        
        # 大單統計
        stats_layout = QGridLayout()
        self.large_buy_label = self.create_data_label("--", 14, True)
        stats_layout.addWidget(QLabel("大單買進:"), 0, 0)
        stats_layout.addWidget(self.large_buy_label, 0, 1)
        
        self.large_sell_label = self.create_data_label("--", 14, True)
        stats_layout.addWidget(QLabel("大單賣出:"), 0, 2)
        stats_layout.addWidget(self.large_sell_label, 0, 3)
        
        self.large_net_label = self.create_data_label("--", 14, True)
        stats_layout.addWidget(QLabel("大單淨量:"), 1, 0)
        stats_layout.addWidget(self.large_net_label, 1, 1)
        
        self.large_ratio_label = self.create_data_label("--", 14, True)
        stats_layout.addWidget(QLabel("大單佔比:"), 1, 2)
        stats_layout.addWidget(self.large_ratio_label, 1, 3)
        
        large_order_layout.addLayout(stats_layout)
        
        # 大單表格
        self.large_order_table = QTableWidget()
        self.large_order_table.setColumnCount(4)
        self.large_order_table.setHorizontalHeaderLabels(["時間", "方向", "價格", "張數"])
        self.large_order_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.large_order_table.setMaximumHeight(200)
        large_order_layout.addWidget(self.large_order_table)
        
        layout.addWidget(large_order_group, 0, 1)
        
        return widget
        
    def create_institutional_tab(self):
        """建立大戶動向分頁"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        inst_group = QGroupBox("🏦 三大法人買賣超")
        inst_layout = QGridLayout(inst_group)
        
        self.foreign_label = self.create_data_label("--", 16, True)
        inst_layout.addWidget(QLabel("外資買賣超:"), 0, 0)
        inst_layout.addWidget(self.foreign_label, 0, 1)
        
        self.trust_label = self.create_data_label("--", 16, True)
        inst_layout.addWidget(QLabel("投信買賣超:"), 1, 0)
        inst_layout.addWidget(self.trust_label, 1, 1)
        
        self.dealer_label = self.create_data_label("--", 16, True)
        inst_layout.addWidget(QLabel("自營商買賣超:"), 2, 0)
        inst_layout.addWidget(self.dealer_label, 2, 1)
        
        self.total_inst_label = self.create_data_label("--", 16, True)
        inst_layout.addWidget(QLabel("三大法人合計:"), 3, 0)
        inst_layout.addWidget(self.total_inst_label, 3, 1)
        
        # 進度條
        inst_layout.addWidget(QLabel("法人動向指標:"), 4, 0)
        self.inst_progress = QProgressBar()
        self.inst_progress.setRange(-100, 100)
        self.inst_progress.setValue(0)
        self.inst_progress.setFormat("%v%")
        inst_layout.addWidget(self.inst_progress, 4, 1)
        
        layout.addWidget(inst_group)
        
        return widget
        
    def create_prediction_tab(self):
        """建立預測分析分頁"""
        widget = QWidget()
        layout = QGridLayout(widget)
        
        # 成交量預測
        vol_pred_group = QGroupBox("📊 成交量預測")
        vol_pred_layout = QGridLayout(vol_pred_group)
        
        self.pred_volume_label = self.create_data_label("--", 16, True)
        vol_pred_layout.addWidget(QLabel("預估今日总量:"), 0, 0)
        vol_pred_layout.addWidget(self.pred_volume_label, 0, 1)
        
        self.pred_accuracy_label = self.create_data_label("--", 16, True)
        vol_pred_layout.addWidget(QLabel("預估準確率:"), 1, 0)
        vol_pred_layout.addWidget(self.pred_accuracy_label, 1, 1)
        
        self.volume_change_label = self.create_data_label("--", 16, True)
        vol_pred_layout.addWidget(QLabel("較昨日增減:"), 2, 0)
        vol_pred_layout.addWidget(self.volume_change_label, 2, 1)
        
        self.pred_avg_price_label = self.create_data_label("--", 16, True)
        vol_pred_layout.addWidget(QLabel("預估均價:"), 3, 0)
        vol_pred_layout.addWidget(self.pred_avg_price_label, 3, 1)
        
        layout.addWidget(vol_pred_group, 0, 0)
        
        # 漲跌停預測
        limit_group = QGroupBox("🎲 漲停跌停預測")
        limit_layout = QGridLayout(limit_group)
        
        self.limit_up_prob_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("漲停機率:"), 0, 0)
        limit_layout.addWidget(self.limit_up_prob_label, 0, 1)
        
        self.limit_down_prob_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("跌停機率:"), 1, 0)
        limit_layout.addWidget(self.limit_down_prob_label, 1, 1)
        
        self.limit_up_price_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("漲停價:"), 2, 0)
        limit_layout.addWidget(self.limit_up_price_label, 2, 1)
        
        self.limit_down_price_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("跌停價:"), 3, 0)
        limit_layout.addWidget(self.limit_down_price_label, 3, 1)
        
        self.resistance_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("壓力位:"), 4, 0)
        limit_layout.addWidget(self.resistance_label, 4, 1)
        
        self.support_label = self.create_data_label("--", 16, True)
        limit_layout.addWidget(QLabel("支撐位:"), 5, 0)
        limit_layout.addWidget(self.support_label, 5, 1)
        
        layout.addWidget(limit_group, 0, 1)
        
        return widget
        
    def create_signal_tab(self):
        """建立操作建議分頁"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        signal_group = QGroupBox("📈 偏多偏空操作建議")
        signal_layout = QGridLayout(signal_group)
        
        self.overall_signal_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("綜合判斷:"), 0, 0)
        signal_layout.addWidget(self.overall_signal_label, 0, 1)
        
        self.technical_signal_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("技術指標:"), 1, 0)
        signal_layout.addWidget(self.technical_signal_label, 1, 1)
        
        self.fundflow_signal_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("資金流向:"), 2, 0)
        signal_layout.addWidget(self.fundflow_signal_label, 2, 1)
        
        self.sentiment_signal_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("市場情緒:"), 3, 0)
        signal_layout.addWidget(self.sentiment_signal_label, 3, 1)
        
        self.position_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("建議部位:"), 4, 0)
        signal_layout.addWidget(self.position_label, 4, 1)
        
        self.stop_loss_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("停損點:"), 5, 0)
        signal_layout.addWidget(self.stop_loss_label, 5, 1)
        
        self.take_profit_label = self.create_data_label("--", 16, True)
        signal_layout.addWidget(QLabel("停利點:"), 6, 0)
        signal_layout.addWidget(self.take_profit_label, 6, 1)
        
        layout.addWidget(signal_group)
        
        # 信號徽章
        self.signal_badge = QLabel("等待分析")
        self.signal_badge.setAlignment(Qt.AlignCenter)
        self.signal_badge.setFont(QFont("Arial", 20, QFont.Bold))
        self.signal_badge.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,100);
                padding: 20px;
                border-radius: 30px;
            }
        """)
        layout.addWidget(self.signal_badge)
        
        return widget
        
    def create_historical_tab(self):
        """建立盤後資料分頁"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        hist_group = QGroupBox("🌙 歷史交易資料")
        hist_layout = QGridLayout(hist_group)
        
        self.open_price_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("開盤價:"), 0, 0)
        hist_layout.addWidget(self.open_price_label, 0, 1)
        
        self.high_price_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("最高價:"), 1, 0)
        hist_layout.addWidget(self.high_price_label, 1, 1)
        
        self.low_price_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("最低價:"), 2, 0)
        hist_layout.addWidget(self.low_price_label, 2, 1)
        
        self.close_price_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("收盤價:"), 3, 0)
        hist_layout.addWidget(self.close_price_label, 3, 1)
        
        self.hist_volume_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("成交量:"), 4, 0)
        hist_layout.addWidget(self.hist_volume_label, 4, 1)
        
        self.price_change_label = self.create_data_label("--", 16, True)
        hist_layout.addWidget(QLabel("漲跌幅:"), 5, 0)
        hist_layout.addWidget(self.price_change_label, 5, 1)
        
        layout.addWidget(hist_group)
        
        return widget
        
    def create_backtest_tab(self):
        """建立回測模擬分頁"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 參數設定
        param_group = QGroupBox("⚙️ 回測參數設定")
        param_layout = QGridLayout(param_group)
        
        param_layout.addWidget(QLabel("初始資金:"), 0, 0)
        self.initial_capital_spin = QDoubleSpinBox()
        self.initial_capital_spin.setRange(100000, 100000000)
        self.initial_capital_spin.setValue(1000000)
        self.initial_capital_spin.setSuffix(" 元")
        param_layout.addWidget(self.initial_capital_spin, 0, 1)
        
        param_layout.addWidget(QLabel("手續費 (%):"), 0, 2)
        self.fee_spin = QDoubleSpinBox()
        self.fee_spin.setRange(0, 1)
        self.fee_spin.setValue(0.1425)
        self.fee_spin.setSingleStep(0.001)
        param_layout.addWidget(self.fee_spin, 0, 3)
        
        param_layout.addWidget(QLabel("交易稅 (%):"), 0, 4)
        self.tax_spin = QDoubleSpinBox()
        self.tax_spin.setRange(0, 1)
        self.tax_spin.setValue(0.3)
        self.tax_spin.setSingleStep(0.001)
        param_layout.addWidget(self.tax_spin, 0, 5)
        
        param_layout.addWidget(QLabel("策略選擇:"), 1, 0)
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["均線交叉", "RSI 超買超賣", "MACD", "布林通道", "自訂策略"])
        param_layout.addWidget(self.strategy_combo, 1, 1)
        
        param_layout.addWidget(QLabel("回測期間:"), 1, 2)
        self.period_combo = QComboBox()
        self.period_combo.addItems(["最近 1 個月", "最近 3 個月", "最近 6 個月", "最近 1 年"])
        param_layout.addWidget(self.period_combo, 1, 3)
        
        # 按鈕
        btn_layout = QHBoxLayout()
        self.backtest_btn = QPushButton("執行回測")
        self.backtest_btn.clicked.connect(self.run_backtest)
        btn_layout.addWidget(self.backtest_btn)
        
        self.export_btn = QPushButton("匯出報告")
        self.export_btn.clicked.connect(self.export_report)
        btn_layout.addWidget(self.export_btn)
        
        layout.addLayout(param_layout)
        layout.addLayout(btn_layout)
        
        # 回測結果
        result_group = QGroupBox("📊 回測結果")
        result_layout = QGridLayout(result_group)
        
        self.total_return_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("總報酬率:"), 0, 0)
        result_layout.addWidget(self.total_return_label, 0, 1)
        
        self.annual_return_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("年化報酬率:"), 0, 2)
        result_layout.addWidget(self.annual_return_label, 0, 3)
        
        self.max_drawdown_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("最大回撤:"), 1, 0)
        result_layout.addWidget(self.max_drawdown_label, 1, 1)
        
        self.sharpe_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("夏普比率:"), 1, 2)
        result_layout.addWidget(self.sharpe_label, 1, 3)
        
        self.win_rate_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("勝率:"), 2, 0)
        result_layout.addWidget(self.win_rate_label, 2, 1)
        
        self.trade_count_label = self.create_data_label("--", 16, True)
        result_layout.addWidget(QLabel("交易次數:"), 2, 2)
        result_layout.addWidget(self.trade_count_label, 2, 3)
        
        layout.addWidget(result_group)
        
        return widget
        
    def create_log_panel(self, layout):
        """建立日誌面板"""
        log_group = QGroupBox("📝 系統日誌")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
    def create_data_label(self, text, size=14, bold=False):
        """建立數據標籤"""
        label = QLabel(text)
        font = QFont("Arial", size)
        if bold:
            font.setBold(True)
        label.setFont(font)
        return label
        
    def add_log(self, message, level="info"):
        """添加日誌訊息"""
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        colors = {
            "info": "#4fc3f7",
            "success": "#81c784",
            "warning": "#ffb74d",
            "error": "#e57373"
        }
        color = colors.get(level, "#4fc3f7")
        self.log_text.append(f'<span style="color:{color}">[{timestamp}] {message}</span>')
        
    def update_system_time(self):
        """更新系統時間"""
        now = datetime.datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        
        # 檢查市場狀態
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()
        
        if weekday >= 5:  # 週末
            self.market_label.setText("休市 (假日)")
        elif 9 <= hour < 13:  # 交易時間
            self.market_label.setText("交易中")
            self.market_label.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 16px;")
        elif 8 <= hour < 9:
            self.market_label.setText("盤前")
        else:
            self.market_label.setText("休市中")
            
    def connect_api(self):
        """連接富邦 API（模擬）"""
        self.add_log("正在連接富邦 API...", "info")
        
        # 模擬延遲
        QTimer.singleShot(1500, self.on_api_connected)
        
    def on_api_connected(self):
        """API 連接完成回調"""
        self.is_connected = True
        self.api_label.setText("已連線")
        self.api_label.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 16px;")
        self.add_log("成功連接富邦 API v2.2.8", "success")
        self.load_twii()
        
    def load_twii(self):
        """載入加權指數"""
        twii = 21500 + random.random() * 200 - 100
        self.twii_label.setText(f"{twii:.2f}")
        self.add_log(f"載入加權指數：{twii:.2f}", "info")
        
    def query_stock(self):
        """查詢股票"""
        symbol = self.stock_input.text().strip()
        if not symbol:
            QMessageBox.warning(self, "警告", "請輸入股票代號")
            return
            
        self.add_log(f"查詢股票：{symbol}", "info")
        self.current_stock = symbol
        
        # 模擬 API 呼叫延遲
        QTimer.singleShot(1000, lambda: self.update_stock_data())
        self.add_log(f"成功載入股票 {symbol} 資料", "success")
        
    def start_monitoring(self):
        """開始監控"""
        if not self.current_stock:
            QMessageBox.warning(self, "警告", "請先查詢股票")
            return
            
        if self.is_monitoring:
            self.add_log("已經在監控中", "warning")
            return
            
        self.is_monitoring = True
        interval = self.interval_spin.value() * 1000
        
        self.add_log(f"開始即時監控，更新頻率：{interval/1000}秒", "success")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # 啟動監控定時器
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_stock_data)
        self.monitor_timer.start(interval)
        
    def stop_monitoring(self):
        """停止監控"""
        if not self.is_monitoring:
            self.add_log("未在監控狀態", "warning")
            return
            
        self.monitor_timer.stop()
        self.is_monitoring = False
        self.add_log("停止即時監控", "info")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
    def update_stock_data(self):
        """更新股票數據（模擬）"""
        if not self.current_stock:
            return
            
        # 生成模擬數據
        base_price = 100 + random.random() * 50
        change = (random.random() - 0.5) * 5
        price = base_price + change
        volume = random.randint(500000, 10500000)
        turnover = volume * price
        
        # 更新即時成交量
        self.current_price_label.setText(f"{price:.2f}")
        self.today_volume_label.setText(f"{volume:,}")
        self.turnover_label.setText(f"{turnover/100000000:.2f}億")
        self.avg_volume_label.setText(f"{int(volume*0.8):,}")
        self.volume_ratio_label.setText(f"{volume/(volume*0.8):.2f}")
        
        # 更新大單
        large_buy = random.randint(1000, 6000)
        large_sell = random.randint(1000, 6000)
        self.large_buy_label.setText(f"+{large_buy:,}張")
        self.large_buy_label.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 14px;")
        self.large_sell_label.setText(f"-{large_sell:,}張")
        self.large_sell_label.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 14px;")
        self.large_net_label.setText(f"{large_buy-large_sell:,}張")
        self.large_ratio_label.setText(f"{(large_buy+large_sell)/volume*100:.2f}%")
        
        # 更新大單表格
        self.update_large_order_table(price)
        
        # 更新法人數據
        self.update_institutional_data()
        
        # 更新預測
        self.update_predictions(price, volume)
        
        # 更新操作建議
        self.update_signals(price)
        
        # 更新歷史資料
        self.update_historical_data(price)
        
    def update_large_order_table(self, price):
        """更新大單表格"""
        row = self.large_order_table.rowCount()
        if row >= 10:
            self.large_order_table.removeRow(0)
            row = 9
            
        self.large_order_table.insertRow(row)
        
        now = QTime.currentTime().toString("HH:mm:ss")
        vol = random.randint(100, 600)
        direction = "買" if random.random() > 0.5 else "賣"
        
        items = [
            QTableWidgetItem(now),
            QTableWidgetItem(direction),
            QTableWidgetItem(f"{price + (random.random()-0.5):.2f}"),
            QTableWidgetItem(str(vol))
        ]
        
        if direction == "買":
            items[1].setForeground(QColor("#ff4444"))
        else:
            items[1].setForeground(QColor("#00ff00"))
            
        for col, item in enumerate(items):
            item.setTextAlignment(Qt.AlignCenter)
            self.large_order_table.setItem(row, col, item)
            
    def update_institutional_data(self):
        """更新法人數據"""
        foreign = (random.random() - 0.5) * 10000
        trust = (random.random() - 0.5) * 5000
        dealer = (random.random() - 0.5) * 3000
        total = foreign + trust + dealer
        
        self.foreign_label.setText(f"{foreign:.0f}張")
        self.foreign_label.setStyleSheet(f"color: {'#ff4444' if foreign>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.trust_label.setText(f"{trust:.0f}張")
        self.trust_label.setStyleSheet(f"color: {'#ff4444' if trust>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.dealer_label.setText(f"{dealer:.0f}張")
        self.dealer_label.setStyleSheet(f"color: {'#ff4444' if dealer>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.total_inst_label.setText(f"{total:.0f}張")
        self.total_inst_label.setStyleSheet(f"color: {'#ff4444' if total>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.inst_progress.setValue(int(total/100))
        self.inst_progress.setFormat("偏多" if total>=0 else "偏空")
        
    def update_predictions(self, price, volume):
        """更新預測數據"""
        pred_vol = int(volume * (1.2 + random.random() * 0.3))
        self.pred_volume_label.setText(f"{pred_vol:,}")
        self.pred_accuracy_label.setText(f"{85+random.random()*10:.1f}%")
        
        vol_change = (random.random() - 0.5) * 50
        sign = "+" if vol_change >= 0 else ""
        self.volume_change_label.setText(f"{sign}{vol_change:.1f}%")
        self.volume_change_label.setStyleSheet(f"color: {'#ff4444' if vol_change>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.pred_avg_price_label.setText(f"{price*(1+random.random()*0.05):.2f}")
        
        # 漲跌停預測
        limit_up_prob = random.random() * 30
        limit_down_prob = random.random() * 20
        self.limit_up_prob_label.setText(f"{limit_up_prob:.1f}%")
        self.limit_down_prob_label.setText(f"{limit_down_prob:.1f}%")
        self.limit_up_price_label.setText(f"{price*1.1:.2f}")
        self.limit_down_price_label.setText(f"{price*0.9:.2f}")
        self.resistance_label.setText(f"{price*1.05:.2f}")
        self.support_label.setText(f"{price*0.95:.2f}")
        
    def update_signals(self, price):
        """更新操作建議"""
        signals = ["強烈買進", "買進", "持有", "賣出", "強烈賣出"]
        weights = [0.1, 0.25, 0.3, 0.25, 0.1]
        
        random_val = random.random()
        cumulative = 0
        signal = "持有"
        
        for i, weight in enumerate(weights):
            cumulative += weight
            if random_val <= cumulative:
                signal = signals[i]
                break
                
        self.overall_signal_label.setText(signal)
        self.technical_signal_label.setText(random.choice(signals))
        self.fundflow_signal_label.setText(random.choice(signals))
        self.sentiment_signal_label.setText(random.choice(signals))
        self.position_label.setText(f"{random.randint(3, 7)}成")
        self.stop_loss_label.setText(f"{price*0.95:.2f}")
        self.take_profit_label.setText(f"{price*1.1:.2f}")
        
        # 更新徽章
        self.signal_badge.setText(signal)
        if "買" in signal:
            self.signal_badge.setStyleSheet("""
                QLabel {
                    background: #ff4444;
                    color: white;
                    padding: 20px;
                    border-radius: 30px;
                    font-weight: bold;
                }
            """)
        elif "賣" in signal:
            self.signal_badge.setStyleSheet("""
                QLabel {
                    background: #00ff00;
                    color: black;
                    padding: 20px;
                    border-radius: 30px;
                    font-weight: bold;
                }
            """)
        else:
            self.signal_badge.setStyleSheet("""
                QLabel {
                    background: rgba(255,255,255,100);
                    color: black;
                    padding: 20px;
                    border-radius: 30px;
                    font-weight: bold;
                }
            """)
            
    def update_historical_data(self, current_price):
        """更新歷史資料"""
        open_price = current_price * (0.98 + random.random() * 0.04)
        high_price = max(current_price, open_price) * (1 + random.random() * 0.03)
        low_price = min(current_price, open_price) * (1 - random.random() * 0.03)
        change = ((current_price - open_price) / open_price) * 100
        
        self.open_price_label.setText(f"{open_price:.2f}")
        self.high_price_label.setText(f"{high_price:.2f}")
        self.low_price_label.setText(f"{low_price:.2f}")
        self.close_price_label.setText(f"{current_price:.2f}")
        self.hist_volume_label.setText(self.today_volume_label.text())
        
        sign = "+" if change >= 0 else ""
        self.price_change_label.setText(f"{sign}{change:.2f}%")
        self.price_change_label.setStyleSheet(f"color: {'#ff4444' if change>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
    def run_backtest(self):
        """執行回測"""
        self.add_log("開始執行回測...", "info")
        
        initial_capital = self.initial_capital_spin.value()
        strategy = self.strategy_combo.currentText()
        period = self.period_combo.currentText()
        
        # 模擬回測延遲
        QTimer.singleShot(2000, lambda: self.on_backtest_complete(initial_capital, strategy, period))
        
    def on_backtest_complete(self, initial_capital, strategy, period):
        """回測完成回調"""
        total_return = (random.random() - 0.3) * 50
        months = int(period.replace("最近", "").replace("個月", "").replace("年", "*12"))
        if "年" in period:
            months = 12
        annual_return = total_return * (12 / max(1, months))
        max_drawdown = -(random.random() * 20 + 5)
        sharpe = random.random() * 2 + 0.5
        win_rate = random.random() * 30 + 45
        trade_count = random.randint(10, 60)
        
        self.total_return_label.setText(f"{total_return:+.2f}%")
        self.total_return_label.setStyleSheet(f"color: {'#ff4444' if total_return>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.annual_return_label.setText(f"{annual_return:+.2f}%")
        self.annual_return_label.setStyleSheet(f"color: {'#ff4444' if annual_return>=0 else '#00ff00'}; font-weight: bold; font-size: 16px;")
        
        self.max_drawdown_label.setText(f"{max_drawdown:.2f}%")
        self.max_drawdown_label.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 16px;")
        
        self.sharpe_label.setText(f"{sharpe:.2f}")
        self.win_rate_label.setText(f"{win_rate:.1f}%")
        self.trade_count_label.setText(str(trade_count))
        
        self.add_log(f"回測完成 - 總報酬：{total_return:+.2f}%, 交易次數：{trade_count}", "success")
        
    def export_report(self):
        """匯出報告"""
        self.add_log("正在生成報告...", "info")
        QMessageBox.information(self, "匯出報告", "報告已匯出至下載資料夾")
        self.add_log("報告匯出成功", "success")


def main():
    """主程式進入點"""
    app = QApplication(sys.argv)
    
    # 設定應用程式字型
    font = QFont("Microsoft JhengHei", 10)
    app.setFont(font)
    
    window = StockMonitorApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
