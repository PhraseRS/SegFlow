# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

class MetricsPlotWidget(QWidget):
    """
    实时的训练指标和验证集指标绘图组件。
    上方绘制 Training Loss，下方绘制 Validation mIoU / mAcc。
    基于 pyqtgraph，保证即使上万个点也非常流畅。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 数据缓存
        self.train_iters = []
        self.train_losses = []
        self.val_iters = []
        self.val_mious = []
        self.val_maccs = []
        
        if not HAS_PYQTGRAPH:
            fallback_label = QLabel(
                "⚠️ 未检测到 pyqtgraph 库，无法显示实时图表。<br>"
                "请在终端运行：<b>pip install pyqtgraph</b><br>然后重启本软件。"
            )
            fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback_label.setStyleSheet("color: red; font-size: 14px;")
            self.layout.addWidget(fallback_label)
            return
            
        # 设置 pyqtgraph 全局背景为白色，前景色为黑色（更适应白天模式），也可选用暗黑。
        pg.setConfigOption('background', '#FFFFFF')
        pg.setConfigOption('foreground', '#333333')
        pg.setConfigOptions(antialias=True) # 开启抗锯齿
        
        # 1. 训练 Loss 图表 (上方)
        self.loss_plot = pg.PlotWidget(title="Training Loss")
        self.loss_plot.showGrid(x=True, y=True, alpha=0.3)
        self.loss_plot.setLabel('left', 'Loss')
        self.loss_plot.setLabel('bottom', 'Iteration (iters)')
        self.loss_curve = self.loss_plot.plot(pen=pg.mkPen(color='#FF5722', width=2))
        
        # 2. 验证集 Metrics 图表 (下方)
        self.val_plot = pg.PlotWidget(title="Validation Metrics (mIoU & mAcc)")
        self.val_plot.showGrid(x=True, y=True, alpha=0.3)
        self.val_plot.setLabel('left', 'Metric (%)')
        self.val_plot.setLabel('bottom', 'Iteration (iters)')
        
        # mIoU 使用蓝色实心点线，mAcc 使用绿色实心点线
        self.miou_curve = self.val_plot.plot(
            pen=pg.mkPen(color='#2196F3', width=2), 
            symbol='o', symbolBrush='#2196F3', symbolSize=6, name='mIoU'
        )
        self.macc_curve = self.val_plot.plot(
            pen=pg.mkPen(color='#4CAF50', width=2), 
            symbol='t', symbolBrush='#4CAF50', symbolSize=6, name='mAcc'
        )
        
        # 添加图例
        self.val_plot.addLegend()
        
        # X 轴联动：拖拽下方图表时，上方图表同步平移缩放
        self.loss_plot.setXLink(self.val_plot)
        
        self.layout.addWidget(self.loss_plot)
        self.layout.addWidget(self.val_plot)
    def update_train_loss(self, iter_num: int, loss: float):
        """插入一条训练 Loss 记录，如果成功更新则重绘折线。"""
        if not HAS_PYQTGRAPH:
            return
            
        self.train_iters.append(iter_num)
        self.train_losses.append(loss)
        
        # 每隔几个点或实时 set_data 都可以，pyqtgraph 性能足够
        self.loss_curve.setData(self.train_iters, self.train_losses)
        
    def update_val_metric(self, iter_num: int, miou: float, macc: float = 0.0):
        """插入一条验证集指标记录。"""
        if not HAS_PYQTGRAPH:
            return
            
        # 注意有可能收到离散的 iter 点，所以保证 x 轴对齐
        self.val_iters.append(iter_num)
        self.val_mious.append(miou)
        self.val_maccs.append(macc)
        
        self.miou_curve.setData(self.val_iters, self.val_mious)
        self.macc_curve.setData(self.val_iters, self.val_maccs)
        
    def clear_plots(self):
        """在下一次训练开始前清理历史残影"""
        self.train_iters.clear()
        self.train_losses.clear()
        self.val_iters.clear()
        self.val_mious.clear()
        self.val_maccs.clear()
        if HAS_PYQTGRAPH:
            self.loss_curve.setData([], [])
            self.miou_curve.setData([], [])
            self.macc_curve.setData([], [])
