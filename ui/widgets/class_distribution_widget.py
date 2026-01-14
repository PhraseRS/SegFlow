# -*- coding: utf-8 -*-
"""
类别分布卡片 (Class Distribution Card) - 紧凑布局版
显示语义分割数据集的类别平衡情况
"""

from typing import Optional, Dict, List, Any
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QCheckBox,
    QPushButton, QButtonGroup, QSizePolicy, QToolButton
)
from PySide6.QtCore import Qt, Signal

# Matplotlib 嵌入式
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
import matplotlib.pyplot as plt

# 配置 Matplotlib 支持中文字体
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


class ClassDistributionChart(FigureCanvas):
    """类别分布图表（Matplotlib 嵌入式）- 紧凑版"""
    
    # 信号：点击某个类别
    bar_clicked = Signal(int)  # class_id
    
    # ==================== 样式配置 ====================
    # 条形尺寸（像素单位）
    BAR_HEIGHT_PX = 10      # 每个条形高度
    BAR_GAP_PX = 6          # 条形间距
    PADDING_PX = 6          # 上下边距
    
    # 条形样式
    BAR_ROUNDING_PX = 0     # 圆角半径（像素），0=无圆角
    BAR_COLOR_BASE = (0.35, 0.65, 0.35)  # 基础颜色 (RGB, 0-1)
    BAR_COLOR_VARIATION = 0.3  # 颜色变化幅度
    
    # 文字样式
    LABEL_FONT_SIZE = 7     # Y轴标签字号
    VALUE_FONT_SIZE = 6     # 数值字号
    VALUE_COLOR = '#555'    # 数值颜色
    VALUE_OFFSET = 0.03     # 数值与条形的间距比例
    # ================================================
    
    def __init__(self, parent: Optional[QWidget] = None, dpi: int = 100):
        self._dpi = dpi
        # 创建 Figure，初始高度较小
        self.fig = Figure(figsize=(3, 0.8), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # 设置大小策略 - 固定高度模式
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(40)
        
        # 数据
        self._class_vals: List[str] = []
        self._pixel_counts: List[int] = []
        self._image_counts: List[int] = []
        self._bars = None
        self._bar_class_map: Dict[int, int] = {}
        
        # 显示选项
        self._show_pixel_count = True
        self._log_scale = False
        self._hide_background = False
        
        # 连接点击事件
        self.mpl_connect('button_press_event', self._on_click)
        
        # 初始化空图表
        self._draw_empty()
    
    def _draw_empty(self) -> None:
        """绘制空图表"""
        self.axes.clear()
        self.axes.text(0.5, 0.5, '暂无数据', ha='center', va='center',
                       transform=self.axes.transAxes, fontsize=9, color='gray')
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        for spine in self.axes.spines.values():
            spine.set_visible(False)
        # 设置固定高度
        self.setFixedHeight(40)
        self.fig.tight_layout(pad=0.1)
        self.draw()
    
    def set_data(self, class_vals: List[str], pixel_counts: List[int], 
                 image_counts: List[int]) -> None:
        """设置数据"""
        self._class_vals = class_vals
        self._pixel_counts = pixel_counts
        self._image_counts = image_counts
        self._update_chart()
    
    def set_show_pixel_count(self, show_pixel: bool) -> None:
        self._show_pixel_count = show_pixel
        self._update_chart()
    
    def set_log_scale(self, log_scale: bool) -> None:
        self._log_scale = log_scale
        self._update_chart()
    
    def set_hide_background(self, hide: bool) -> None:
        self._hide_background = hide
        self._update_chart()
    
    def _update_chart(self) -> None:
        """更新图表 - 使用统一样式配置"""
        self.axes.clear()
        
        if not self._class_vals:
            self._draw_empty()
            return
        
        # 准备数据
        class_vals = self._class_vals.copy()
        counts = self._pixel_counts.copy() if self._show_pixel_count else self._image_counts.copy()
        
        # 隐藏背景类
        if self._hide_background and len(class_vals) > 0:
            try:
                bg_idx = class_vals.index('0')
                class_vals.pop(bg_idx)
                counts.pop(bg_idx)
            except ValueError:
                pass
        
        if not class_vals:
            self._draw_empty()
            return
        
        n_classes = len(class_vals)
        counts = np.array(counts, dtype=float)
        
        # 计算固定高度（像素）
        total_height_px = n_classes * self.BAR_HEIGHT_PX + (n_classes - 1) * self.BAR_GAP_PX + 2 * self.PADDING_PX
        total_height_px = max(total_height_px, 40)
        
        # 更新 Figure 高度
        fig_height_inch = total_height_px / self._dpi
        self.fig.set_size_inches(self.fig.get_figwidth(), fig_height_inch)
        self.setFixedHeight(total_height_px)
        
        # 对数坐标处理
        if self._log_scale:
            min_nonzero = counts[counts > 0].min() if np.any(counts > 0) else 1
            display_counts = np.maximum(counts, min_nonzero * 0.1)
            display_counts = np.log10(display_counts + 1)
        else:
            max_count = counts.max() if counts.max() > 0 else 1
            min_display = max_count * 0.02
            display_counts = np.maximum(counts, min_display)
        
        # 颜色映射 - 使用配置的基础颜色
        base_color = np.array(self.BAR_COLOR_BASE)
        colors = [base_color * (1.0 - self.BAR_COLOR_VARIATION + self.BAR_COLOR_VARIATION * i / max(n_classes - 1, 1)) 
                  for i in range(n_classes)]
        
        # 条形高度（相对单位）- 固定比例
        bar_height = 0.6  # 固定相对高度
        
        # 圆角半径（相对单位）- 基于像素配置转换
        # 将像素圆角转换为相对单位
        rounding = bar_height * 0.5 if self.BAR_ROUNDING_PX > 0 else 0
        
        # 绘制条形图
        max_width = display_counts.max()
        self._bars = []
        self._bar_class_map.clear()
        
        y_pos = np.arange(n_classes)
        
        for i, (y, width, count, cv) in enumerate(zip(y_pos, display_counts, counts, class_vals)):
            # 创建条形
            if rounding > 0:
                bar = FancyBboxPatch(
                    (0, y - bar_height / 2),
                    width, bar_height,
                    boxstyle=f"round,pad=0,rounding_size={rounding}",
                    facecolor=colors[i % len(colors)],
                    edgecolor='none',
                    linewidth=0
                )
            else:
                bar = FancyBboxPatch(
                    (0, y - bar_height / 2),
                    width, bar_height,
                    boxstyle="square,pad=0",
                    facecolor=colors[i % len(colors)],
                    edgecolor='none',
                    linewidth=0
                )
            self.axes.add_patch(bar)
            self._bars.append(bar)
            
            # 建立映射
            try:
                self._bar_class_map[i] = int(cv)
            except ValueError:
                self._bar_class_map[i] = i
            
            # 在条形后显示数值
            if self._show_pixel_count:
                if count >= 1e9:
                    text = f'{count/1e9:.1f}B'
                elif count >= 1e6:
                    text = f'{count/1e6:.1f}M'
                elif count >= 1e3:
                    text = f'{count/1e3:.1f}K'
                else:
                    text = f'{int(count)}'
            else:
                text = f'{int(count):,}'
            
            x_pos = width + max_width * self.VALUE_OFFSET
            self.axes.text(x_pos, y, text, va='center', ha='left', 
                          fontsize=self.VALUE_FONT_SIZE, color=self.VALUE_COLOR)
        
        # Y轴标签
        labels = [f"C{cv}" for cv in class_vals]
        self.axes.set_yticks(y_pos)
        self.axes.set_yticklabels(labels, fontsize=self.LABEL_FONT_SIZE)
        
        # 隐藏坐标轴
        self.axes.set_xticks([])
        self.axes.invert_yaxis()
        for spine in self.axes.spines.values():
            spine.set_visible(False)
        
        # 设置范围
        self.axes.set_xlim(0, max_width * 1.35)
        self.axes.set_ylim(n_classes - 0.5, -0.5)
        
        self.fig.tight_layout(pad=0.1)
        self.draw()
    
    def _on_click(self, event) -> None:
        if event.inaxes != self.axes or not self._bars:
            return
        for i, bar in enumerate(self._bars):
            if bar.contains(event)[0]:
                self.bar_clicked.emit(self._bar_class_map.get(i, i))
                break


class ClassDistributionWidget(QWidget):
    """类别分布卡片组件 - 紧凑布局版"""
    
    classClicked = Signal(int)
    weightsCalculated = Signal(list)
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._stats: Dict[str, Any] = {}
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self) -> None:
        """初始化UI - 紧凑版，顶部对齐"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # === 单行控制栏：Pixel/Image + Log + HideBG ===
        control_layout = QHBoxLayout()
        control_layout.setSpacing(6)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # RadioButton 切换
        self.radio_pixel = QRadioButton("Px")
        self.radio_image = QRadioButton("Img")
        self.radio_pixel.setChecked(True)
        self.radio_pixel.setStyleSheet("font-size: 10px; padding: 0;")
        self.radio_image.setStyleSheet("font-size: 10px; padding: 0;")
        
        self.radio_group = QButtonGroup(self)
        self.radio_group.addButton(self.radio_pixel, 0)
        self.radio_group.addButton(self.radio_image, 1)
        
        control_layout.addWidget(self.radio_pixel)
        control_layout.addWidget(self.radio_image)
        control_layout.addSpacing(8)
        
        # CheckBox
        self.check_log = QCheckBox("Log")
        self.check_log.setStyleSheet("font-size: 10px; padding: 0;")
        control_layout.addWidget(self.check_log)
        
        self.check_hide_bg = QCheckBox("NoBG")
        self.check_hide_bg.setStyleSheet("font-size: 10px; padding: 0;")
        self.check_hide_bg.setToolTip("隐藏背景类 (Class 0)")
        control_layout.addWidget(self.check_hide_bg)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # === 图表区域 ===
        self.chart = ClassDistributionChart(self)
        layout.addWidget(self.chart, 0, Qt.AlignmentFlag.AlignTop)  # 顶部对齐，不拉伸
        
        # 底部弹性空间，确保内容顶部对齐
        layout.addStretch()
        
        # === 权重按钮（供外部添加到标题栏）===
        self.btn_calc_weights = QToolButton()
        self.btn_calc_weights.setText("📊 计算权重")
        self.btn_calc_weights.setToolTip("计算类别权重 (Median Frequency Balancing)")
        self.btn_calc_weights.setStyleSheet("""
            QToolButton {
                font-size: 10px;
                padding: 2px 8px;
                border: 1px solid palette(mid);
                border-radius: 3px;
                background: transparent;
            }
            QToolButton:hover { background-color: palette(light); }
            QToolButton:disabled { color: gray; }
        """)
        self.btn_calc_weights.setEnabled(False)
        self.btn_calc_weights.setParent(None)  # 不添加到布局，供外部使用
    
    def get_header_button(self) -> QToolButton:
        """获取权重计算按钮，供添加到折叠面板标题栏"""
        return self.btn_calc_weights
    
    def _connect_signals(self) -> None:
        self.radio_group.idToggled.connect(self._on_count_type_changed)
        self.check_log.toggled.connect(self.chart.set_log_scale)
        self.check_hide_bg.toggled.connect(self.chart.set_hide_background)
        self.chart.bar_clicked.connect(self.classClicked.emit)
        self.btn_calc_weights.clicked.connect(self._on_calc_weights)
    
    def _on_count_type_changed(self, id: int, checked: bool) -> None:
        if checked:
            self.chart.set_show_pixel_count(id == 0)
    
    def _on_calc_weights(self) -> None:
        """计算类别权重（Median Frequency Balancing）"""
        if not self._stats:
            return
        
        pixel_counts = self._stats.get('pixel_counts', [])
        if not pixel_counts:
            return
        
        counts = np.array(pixel_counts, dtype=float)
        total = counts.sum()
        if total == 0:
            return
        
        freqs = counts / total
        freqs = np.maximum(freqs, 1e-10)
        median_freq = np.median(freqs[freqs > 1e-10])
        weights = median_freq / freqs
        weights = weights / weights.min()
        
        self.weightsCalculated.emit(weights.tolist())
        
        print("📊 [ClassDistribution] Weights:", 
              {cv: f"{w:.2f}" for cv, w in zip(self._stats.get('class_vals', []), weights)})
    
    def set_data(self, stats: Dict[str, Any]) -> None:
        self._stats = stats
        class_vals = stats.get('class_vals', [])
        pixel_counts = stats.get('pixel_counts', [])
        image_counts = stats.get('image_counts', [])
        self.chart.set_data(class_vals, pixel_counts, image_counts)
        self.btn_calc_weights.setEnabled(len(pixel_counts) > 0)
    
    def clear(self) -> None:
        self._stats = {}
        self.chart.set_data([], [], [])
        self.btn_calc_weights.setEnabled(False)
    
    def get_weights(self) -> Optional[List[float]]:
        if not self._stats:
            return None
        pixel_counts = self._stats.get('pixel_counts', [])
        if not pixel_counts:
            return None
        counts = np.array(pixel_counts, dtype=float)
        total = counts.sum()
        if total == 0:
            return None
        freqs = counts / total
        freqs = np.maximum(freqs, 1e-10)
        median_freq = np.median(freqs[freqs > 1e-10])
        weights = median_freq / freqs
        return (weights / weights.min()).tolist()
