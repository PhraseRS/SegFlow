# -*- coding: utf-8 -*-
"""
数据智能推荐配置组件 (Advisor Config Widget)

以摘要列表形式展示 ConfigAdvisor 传来的推荐参数，
并提供"一键全部应用"按钮，一键触发外部所有关联组件的推荐采纳。

Training Roadmap Phase 3, Task 3.2
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Signal, Qt


class AdvisorConfigWidget(QWidget):
    """
    数据智能推荐组件 (精简摘要版)
    """

    # 当用户点击一键应用时发出，携带原始的 rs_params 字典
    apply_all_requested = Signal(dict)
    
    # 发起推荐生成请求
    generate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._advisor_params = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 生成推荐按钮 (默认状态下显示)
        self.btn_generate = QPushButton("✨ Get Data-Driven Recommendations")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #F3E5F5;
                color: #6A1B9A;
                font-weight: bold;
                border: 1px solid #CE93D8;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #E1BEE7;
            }
        """)
        self.btn_generate.clicked.connect(self.generate_requested.emit)
        layout.addWidget(self.btn_generate)

        # 状态标签 (加载时显示)
        self.label_status = QLabel("⏳ Generating recommended config based on analysis...")
        self.label_status.setStyleSheet("color: #666; font-style: italic; padding: 4px;")
        self.label_status.setVisible(False)
        layout.addWidget(self.label_status)

        # 推荐摘要容器
        self.widget_summary = QWidget()
        self.layout_summary = QVBoxLayout(self.widget_summary)
        self.layout_summary.setContentsMargins(0, 0, 0, 0)
        self.layout_summary.setSpacing(4)
        
        self.widget_summary.setVisible(False)
        layout.addWidget(self.widget_summary)

        # 一键应用按钮
        self.btn_apply_all = QPushButton("✅ Apply All")
        self.btn_apply_all.setStyleSheet("""
            QPushButton {
                background-color: #E3F2FD;
                color: #1565C0;
                font-weight: bold;
                border: 1px solid #90CAF9;
                border-radius: 4px;
                padding: 6px;
                margin-top: 8px;
            }
            QPushButton:hover {
                background-color: #BBDEFB;
            }
        """)
        self.btn_apply_all.setVisible(False)
        self.btn_apply_all.clicked.connect(self._on_apply_all)
        layout.addWidget(self.btn_apply_all)
        
        layout.addStretch()

    def set_advisor_params(self, params: dict):
        """
        填充推荐参数并生成摘要。
        """
        self._advisor_params = params
        
        # 清空旧的摘要
        while self.layout_summary.count():
            item = self.layout_summary.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # 顶部Tip
        num_items = 0
        
        # 分析并添加摘要项
        if 'in_channels' in params:
            lbl = QLabel(f"· <b>In Channels</b>: Recommend <b>{params['in_channels']}</b> <span style='color: #666;'>(Affected by image bands)</span>")
            lbl.setTextFormat(Qt.RichText)
            self.layout_summary.addWidget(lbl)
            num_items += 1
            
        if 'crop_size' in params:
            crop = params['crop_size']
            crop_val = crop[0] if isinstance(crop, (list, tuple)) else crop
            lbl = QLabel(f"· <b>Crop Size</b>: Recommend <b>{crop_val}</b> <span style='color: #666;'>(Based on min image width × 0.8)</span>")
            lbl.setTextFormat(Qt.RichText)
            self.layout_summary.addWidget(lbl)
            num_items += 1
            
        if 'class_weight' in params and params['class_weight']:
            lbl = QLabel(f"· <b>Loss Weighting</b>: Recommend <b>Enable</b> <span style='color: #666;'>(For class imbalance)</span>")
            lbl.setTextFormat(Qt.RichText)
            self.layout_summary.addWidget(lbl)
            num_items += 1
            
        if 'loss_config' in params and params['loss_config'] and 'type' in params['loss_config']:
            lbl = QLabel(f"· <b>Loss Function</b>: Recommend <b>{params['loss_config']['type']}</b> <span style='color: #666;'>({params['loss_config'].get('_reason', '')})</span>")
            lbl.setTextFormat(Qt.RichText)
            self.layout_summary.addWidget(lbl)
            num_items += 1

        if num_items > 0:
            header = QLabel(f"💡 Based on dataset features, generated <b>{num_items}</b> recommendations waiting to be applied:")
            header.setTextFormat(Qt.RichText)
            self.layout_summary.insertWidget(0, header)
            
            note = QLabel("⚠ Recommendations will be distributed to respective fields (marked with 💡)\nYou can also click the lightbulb icons individually to apply.")
            note.setStyleSheet("color: #888; font-size: 11px;")
            self.layout_summary.addWidget(note)

        self.btn_generate.setVisible(False)
        self.label_status.setVisible(False)
        self.widget_summary.setVisible(num_items > 0)
        self.btn_apply_all.setVisible(num_items > 0)

    def clear(self):
        """清空推荐参数，恢复未生成状态"""
        self._advisor_params = {}
        self.btn_generate.setVisible(True)
        self.label_status.setVisible(False)
        self.widget_summary.setVisible(False)
        self.btn_apply_all.setVisible(False)
        
    def show_loading(self):
        """显示生成中的等待状态"""
        self.btn_generate.setVisible(False)
        self.label_status.setVisible(True)
        self.widget_summary.setVisible(False)
        self.btn_apply_all.setVisible(False)

    def _on_apply_all(self):
        """发送信号通知外部控制器"""
        self.apply_all_requested.emit(self._advisor_params)
        
    def get_params(self) -> dict:
        """
        收集当前配置参数。
        
        注意：新的设计下，推荐参数将直接通过 controller 写入 HyperparamTabsWidget 
        或 AdvancedConfigWidget 的对应部件中，因此 ConfigAggregator 不再需要 
        AdvisorConfigWidget 强力覆盖。
        此方法仅返回空字典以免产生冲突的覆盖源。
        """
        return {}
