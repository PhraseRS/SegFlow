# -*- coding: utf-8 -*-
"""
TaskConfigDashboard - 任务配置与训练执行中心仪表盘 (Visual Dashboard)
提供配置管线蓝图、数据增强预览、健康度打分，以及训练过程监控界面的占位。

严格遵循系统浅色主题规范与布局尺寸约束 (自适应填充但不强制撑大)。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QStackedWidget,
    QSizePolicy, QProgressBar, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPixmap, QImage
import os
import cv2
import numpy as np

try:
    from ui.widgets.metrics_plot_widget import MetricsPlotWidget
    _HAS_METRICS_PLOT = True
except ImportError:
    _HAS_METRICS_PLOT = False


class PipelineNode(QFrame):
    """蓝图中单个管线节点组件。
    大小固定，文字超长时自动换行。
    """
    def __init__(self, title: str, detail: str = "TBD", parent=None):
        super().__init__(parent)
        self.setProperty("active", False)
        
        # 节点基础样式支持浅色主题
        self.setStyleSheet("""
            PipelineNode {
                background-color: #F8F9FA;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
            }
            PipelineNode[active="true"] {
                background-color: #E3F2FD;
                border: 2px solid #2196F3;
            }
            PipelineNode[active="false"] {
                background-color: #F8F9FA;
                border: 1px solid #DEE2E6;
            }
        """)
        
        # 水平布局：Expanding 允许拉伸占满差分布空间，
        # 但绝对不根据内容向外撑大
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        # 限定节点的最小和最大高度，防止垂直方向撤大
        self.setMinimumHeight(72)
        self.setMaximumHeight(96)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #343A40;")
        # 标题占据固定比例，不根据内容扩张
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )
        
        self.detail_label = QLabel(detail)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        self.detail_label.setWordWrap(True)  # 自动换行
        self.detail_label.setStyleSheet("color: #6C757D; font-size: 10px;")
        self.detail_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding   # 展开向下填充剩余高度
        )
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        
    def set_active(self, active: bool, detail: str = None):
        """更新节点激活状态与参数文本"""
        self.setProperty("active", active)
        if detail is not None:
            self.detail_label.setText(detail)
        
        # 刷新样式
        self.style().unpolish(self)
        self.style().polish(self)


class PipelineBlueprintWidget(QWidget):
    """训练管线蓝图可视化组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 定义 5 个核心节点
        self.nodes = {
            "dataset": PipelineNode("Dataset"),
            "aug": PipelineNode("Augmentation"),
            "model": PipelineNode("Model"),
            "loss": PipelineNode("Loss & Opt"),
            "output": PipelineNode("Output")
        }
        
        # 将节点与箭头连接
        keys = list(self.nodes.keys())
        for i, key in enumerate(keys):
            layout.addWidget(self.nodes[key], 1)
            if i < len(keys) - 1:
                arrow = QLabel("➡️")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet("color: #ADB5BD; font-size: 14px;")
                layout.addWidget(arrow, 0)


class AugmentationPreviewStrip(QWidget):
    """样本增强实时预览网格"""
    PREVIEW_SIZE = 128
    ROW_COUNT = 3
    AUGMENTATION_COLUMNS = [
        ("original", "Original"),
        ("flip", "Flip"),
        ("color", "Color"),
        ("rotate", "Rotate"),
        ("multiscale", "MultiScale"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview_data = []
        self.augmentation_states = {
            "flip": True,
            "color": True,
            "rotate": False,
            "multiscale": False,
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Live Augmentation Preview")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background-color: transparent;")

        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setContentsMargins(0, 8, 0, 8)
        self.grid_layout.setHorizontalSpacing(16)
        self.grid_layout.setVerticalSpacing(12)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self._render_grid()

    def _clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _read_image_cv(self, img_path: str):
        if not img_path or not os.path.exists(img_path):
            return None
        try:
            img_data = np.fromfile(img_path, dtype=np.uint8)
            if img_data.size == 0:
                return None
            return cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def _cv_to_pixmap(self, img_cv, size: int = None) -> QPixmap:
        if img_cv is None:
            return QPixmap()
        size = size or self.PREVIEW_SIZE
        rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg).scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _simulate_augmentation(self, img_cv, aug_key: str):
        if img_cv is None:
            return None

        if aug_key == "original":
            return img_cv.copy()
        if aug_key == "flip":
            return cv2.flip(img_cv, 1)
        if aug_key == "color":
            return cv2.convertScaleAbs(img_cv, alpha=1.15, beta=22)
        if aug_key == "rotate":
            h, w = img_cv.shape[:2]
            center = (w / 2, h / 2)
            matrix = cv2.getRotationMatrix2D(center, 18, 1.0)
            return cv2.warpAffine(
                img_cv,
                matrix,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT_101,
            )
        if aug_key == "multiscale":
            h, w = img_cv.shape[:2]
            scale = 1.2
            resized = cv2.resize(img_cv, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
            new_h, new_w = resized.shape[:2]
            start_y = max((new_h - h) // 2, 0)
            start_x = max((new_w - w) // 2, 0)
            cropped = resized[start_y:start_y + h, start_x:start_x + w]
            if cropped.shape[:2] != (h, w):
                cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
            return cropped
        return img_cv.copy()

    def _make_image_label(self, pixmap: QPixmap = None, text: str = "", is_placeholder: bool = False) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedSize(self.PREVIEW_SIZE, self.PREVIEW_SIZE)
        if is_placeholder:
            label.setStyleSheet("background-color: #000000; border-radius: 6px; color: #495057;")
        else:
            label.setStyleSheet("background-color: #E9ECEF; border-radius: 6px; color: #6C757D;")
        if pixmap is not None and not pixmap.isNull():
            label.setPixmap(pixmap)
        else:
            label.setText(text)
        return label

    def _make_cell_widget(self, title_text: str, pixmap: QPixmap = None, text: str = "", is_placeholder: bool = False):
        cell = QWidget()
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(6)

        img_label = self._make_image_label(pixmap=pixmap, text=text, is_placeholder=is_placeholder)
        caption = QLabel(title_text)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet("color: #495057; font-size: 11px; font-weight: bold;")

        cell_layout.addWidget(img_label, alignment=Qt.AlignmentFlag.AlignCenter)
        cell_layout.addWidget(caption)
        return cell

    def _render_grid(self):
        self._clear_grid()

        for col, (_, header_text) in enumerate(self.AUGMENTATION_COLUMNS):
            header = QLabel(header_text)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet("color: #212529; font-size: 11px; font-weight: bold;")
            self.grid_layout.addWidget(header, 0, col)

        rows = self.preview_data[:self.ROW_COUNT]
        for row_index in range(self.ROW_COUNT):
            sample = rows[row_index] if row_index < len(rows) else None
            img_cv = self._read_image_cv(sample.get('img_path', '')) if sample else None
            sample_name = sample.get('name', f'Sample {row_index + 1}') if sample else f'Sample {row_index + 1}'

            for col_index, (aug_key, _) in enumerate(self.AUGMENTATION_COLUMNS):
                if sample is None:
                    cell = self._make_cell_widget(
                        sample_name if aug_key == "original" else ("Disabled" if not self.augmentation_states.get(aug_key, False) else "Waiting for samples"),
                        text="No Samples" if aug_key == "original" else "",
                        is_placeholder=(aug_key != "original" and not self.augmentation_states.get(aug_key, False)),
                    )
                else:
                    if aug_key == "original":
                        pixmap = self._cv_to_pixmap(self._simulate_augmentation(img_cv, aug_key))
                        cell = self._make_cell_widget(sample_name, pixmap=pixmap, text="No Image")
                    elif self.augmentation_states.get(aug_key, False):
                        pixmap = self._cv_to_pixmap(self._simulate_augmentation(img_cv, aug_key))
                        cell = self._make_cell_widget(sample_name, pixmap=pixmap, text="No Preview")
                    else:
                        cell = self._make_cell_widget("Disabled", is_placeholder=True)
                self.grid_layout.addWidget(cell, row_index + 1, col_index)

        self.grid_layout.setColumnStretch(len(self.AUGMENTATION_COLUMNS), 1)

    def set_augmentation_states(self, states: dict):
        self.augmentation_states.update({
            "flip": bool(states.get("flip", self.augmentation_states["flip"])),
            "color": bool(states.get("color", self.augmentation_states["color"])),
            "rotate": bool(states.get("rotate", self.augmentation_states["rotate"])),
            "multiscale": bool(states.get("multiscale", self.augmentation_states["multiscale"])),
        })
        self._render_grid()

    def update_previews(self, preview_data):
        """
        接入真实样本数据
        :param preview_data: list of dicts [{'img_path': str, 'lbl_path': str, 'name': str}]
        """
        self.preview_data = list(preview_data or [])
        self._render_grid()


class ConfigHealthBar(QWidget):
    """配置健康度水平打分条（5维度：数据/参数/显存/增强/环境）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Configuration Health Score")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)

        # 进度条布局
        bar_layout = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v Pts")
        self.progress_bar.setMinimumHeight(24)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #DEE2E6;
                border-radius: 12px;
                text-align: center;
                background-color: #F8F9FA;
                color: #495057;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #20C997;
                border-radius: 11px;
            }
        """)
        bar_layout.addWidget(self.progress_bar, stretch=1)
        layout.addLayout(bar_layout)

        # 徽章布局（新增 env 维度）
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(8)

        self.pills = {
            "vram":   self._create_pill("Est. VRAM: -- GB",  "#F1F3F5", "#495057"),
            "data":   self._create_pill("Dataset: Not Ready",   "#F1F3F5", "#495057"),
            "params": self._create_pill("Params: Pending",     "#F1F3F5", "#495057"),
            "env":    self._create_pill("Env: Not Detected",     "#F1F3F5", "#495057"),
        }

        for p in self.pills.values():
            pills_layout.addWidget(p)
        pills_layout.addStretch()
        layout.addLayout(pills_layout)

        # 订阅 EnvStateManager 状态变化
        from core.env_state_manager import EnvStateManager
        EnvStateManager.instance().state_changed.connect(self._on_env_state_changed)

    def _create_pill(self, text: str, bg_color: str, text_color: str) -> QLabel:
        pill = QLabel(text)
        pill.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 4px 10px;
                border-radius: 10px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        return pill

    def _on_env_state_changed(self, state: dict):
        """响应 EnvStateManager 广播，更新环境 pill（无需重新评分整体）。"""
        if state.get("is_ready"):
            python_path = state.get("python_path", "")
            short_path = python_path.split("\\")[-2] if "\\" in python_path else python_path
            self.update_env_pill(ready=True, label=f"✅ Env: {short_path}")
        else:
            status = state.get("status", "unknown")
            if status == "unknown":
                self.update_env_pill(ready=None, label="Env: Not Detected")
            else:
                self.update_env_pill(ready=False, label="❌ Env: Not Ready")

    def update_env_pill(self, ready, label: str):
        """
        更新环境 pill 状态。
        ready=True  → 绿色
        ready=False → 红色
        ready=None  → 灰色（未检测）
        """
        if ready is True:
            self._pill_update("env", label, "#D4EDDA", "#155724")
        elif ready is False:
            self._pill_update("env", label, "#F8D7DA", "#721C24")
        else:
            self._pill_update("env", label, "#F1F3F5", "#495057")

    def _pill_update(self, name: str, text: str, bg: str, fg: str):
        if name in self.pills:
            pill = self.pills[name]
            pill.setText(text)
            pill.setStyleSheet(
                f"background-color: {bg}; color: {fg}; "
                "padding: 4px 10px; border-radius: 10px; "
                "font-size: 11px; font-weight: bold;"
            )


class TaskConfigBlueprintWidget(QWidget):
    """任务配置视图中心总控面板"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_params: dict = {}
        self._last_dataset_ready: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(24)

        # 标题区
        header = QLabel("Task Configuration Dashboard")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #212529;")
        layout.addWidget(header)

        # 三大核心区块
        self.blueprint = PipelineBlueprintWidget()
        self.preview_strip = AugmentationPreviewStrip()
        self.health_bar = ConfigHealthBar()

        layout.addWidget(self.blueprint, stretch=1)
        layout.addWidget(self.preview_strip, stretch=2)
        layout.addWidget(self.health_bar, stretch=1)

        # 订阅环境状态变化，实时同步健康度评分
        from core.env_state_manager import EnvStateManager
        EnvStateManager.instance().state_changed.connect(self._on_env_state_changed)

        # 默认更新初始状态
        self.update_blueprint({})

    def _on_env_state_changed(self, _state: dict):
        """环境状态变化时，用缓存的参数重新计算健康度评分。"""
        self._update_health_score(self._last_params, self._last_dataset_ready)

    def update_blueprint(self, params: dict):
        """
        根据完整的参数字典更新蓝图各节点与健康度。
        params 整合了 HyperparamTabsWidget / ModelSelectionWidget 以及数据集Info。
        """
        # ---- Dataset 节点 ----
        dataset_samples = params.get("dataset_samples", 0)
        data_root = params.get("data_root", "")
        dataset_ready = bool(dataset_samples > 0 or data_root)
        if dataset_ready:
            label = f"{dataset_samples} Samples" if dataset_samples else "Loaded"
            self.blueprint.nodes["dataset"].set_active(True, label)
        else:
            self.blueprint.nodes["dataset"].set_active(False, "Dataset not loaded")

        # ---- Augmentation 节点 ----
        crop_size = params.get("crop_size", 512)
        augmentations = []
        if params.get("aug_random_flip", True):
            augmentations.append("Flip")
        if params.get("aug_photo_distortion", True):
            augmentations.append("Color")
        if params.get("aug_random_rotate", False):
            augmentations.append("Rotate")
        if params.get("aug_multi_scale", False):
            augmentations.append("MultiScale")
        aug_label = f"Crop:{crop_size} \u00b7 " + "+".join(augmentations) if augmentations else f"Crop:{crop_size}"
        self.blueprint.nodes["aug"].set_active(len(params) > 0, aug_label)
        self.preview_strip.set_augmentation_states({
            "flip": params.get("aug_random_flip", True),
            "color": params.get("aug_photo_distortion", True),
            "rotate": params.get("aug_random_rotate", False),
            "multiscale": params.get("aug_multi_scale", False),
        })

        # ---- Model 节点 ----
        method = params.get("method", "")
        backbone = params.get("backbone", "")
        in_ch = params.get("in_channels", 3)

        if method and backbone:
            model_label = f"{method}\n{backbone} | {in_ch}ch"
        elif method:
            model_label = f"{method} | {in_ch}ch"
        elif backbone:
            model_label = f"{backbone} | {in_ch}ch"
        else:
            model_label = "Pending"
        self.blueprint.nodes["model"].set_active(bool(method or backbone), model_label)

        # ---- Loss & Optimizer 节点 ----
        loss_type = params.get("loss_type", "CrossEntropyLoss")
        optimizer = params.get("optimizer", "AdamW")
        lr = params.get("lr", 0.0001)
        lr_sched = params.get("lr_schedule", "PolyLR")
        loss_label = f"{loss_type}\n{optimizer} \u00b7 lr={lr:.1e} \u00b7 {lr_sched}"
        self.blueprint.nodes["loss"].set_active(len(params) > 0, loss_label)

        # ---- Output 节点 ----
        max_iters = params.get("max_iters", 40000)
        val_interval = params.get("val_interval", 4000)
        save_best = "Best\u2713" if params.get("save_best", True) else "Fixed"
        output_label = f"{max_iters} iters\nVal/{val_interval} \u00b7 {save_best}"
        self.blueprint.nodes["output"].set_active(len(params) > 0, output_label)

        # ---- 健康度多维评分 ----
        self._update_health_score(params, dataset_ready)

    def _update_health_score(self, params: dict, dataset_ready: bool):
        """
        5维度加权健康度评分，归一化到100分。

        维度权重（原始分 / 总分 * 100）：
          数据集就绪   20分
          模型参数已选 20分
          显存估算     20分
          关键增强     20分
          环境就绪     20分  ← 由 EnvStateManager 实时更新
        """
        # 缓存参数，供环境状态变化时重新评分
        self._last_params = params
        self._last_dataset_ready = dataset_ready

        raw_score = 0
        MAX_RAW = 100  # 每维度20分，共5维度

        # 1. 数据集就绪（20分）
        if dataset_ready:
            raw_score += 20
            ds = params.get('dataset_samples', 0)
            self.pills_status_update("data", f"✅ Data: {ds or ''}Ready", "#D4EDDA", "#155724")
        else:
            self.pills_status_update("data", "⚠ Data: Not Loaded", "#FFF3CD", "#856404")

        # 2. 模型参数已选（20分）
        if params.get("method") or params.get("backbone"):
            raw_score += 20
            self.pills_status_update("params", "✅ Params: Configured", "#D4EDDA", "#155724")
        else:
            self.pills_status_update("params", "⚠ Params: Pending", "#FFF3CD", "#856404")

        # 3. 批大小与显存估算（20分，超出16GB得0分）
        batch_size = params.get("batch_size", 2)
        crop_size = params.get("crop_size", 512)
        in_ch = params.get("in_channels", 3)
        estimated_vram_gb = round((crop_size ** 2 * in_ch * 4 * batch_size * 4) / 1e9, 1)
        if estimated_vram_gb <= 8:
            raw_score += 20
            self.pills_status_update("vram", f"✅ Est. VRAM: ~{estimated_vram_gb}GB", "#D4EDDA", "#155724")
        elif estimated_vram_gb <= 16:
            raw_score += 12
            self.pills_status_update("vram", f"⚠ Est. VRAM: ~{estimated_vram_gb}GB", "#FFF3CD", "#856404")
        else:
            self.pills_status_update("vram", f"❌ VRAM: ~{estimated_vram_gb}GB OOM风险!", "#F8D7DA", "#721C24")

        # 4. 关键增强选项（20分）
        if params.get("aug_random_flip", False) or params.get("aug_photo_distortion", False):
            raw_score += 20

        # 5. 环境就绪（20分）—— 从 EnvStateManager 读取，不依赖 params
        from core.env_state_manager import EnvStateManager
        env_state = EnvStateManager.instance()
        if env_state.is_ready:
            raw_score += 20
            # env pill 由 _on_env_state_changed 独立维护，此处不重复更新

        # 归一化到100分
        score = min(100, int(raw_score * 100 / MAX_RAW))

        # 更新进度条（含动态Color）
        self.health_bar.progress_bar.setValue(score)
        chunk_color = "#20C997" if score >= 75 else ("#FFC107" if score >= 50 else "#DC3545")
        self.health_bar.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #DEE2E6;
                border-radius: 12px;
                text-align: center;
                background-color: #F8F9FA;
                color: #212529;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 11px;
            }}
        """)

    def pills_status_update(self, name: str, text: str, bg: str, fg: str):
        if name in self.health_bar.pills:
            pill = self.health_bar.pills[name]
            pill.setText(text)
            pill.setStyleSheet(
                f"background-color: {bg}; color: {fg}; "
                "padding: 4px 10px; border-radius: 10px; "
                "font-size: 11px; font-weight: bold;"
            )


class LossCurvePlaceholder(QWidget):
    """专门为动态损失曲线预留的占位空组件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #F8F9FA;
                border: 2px dashed #CED4DA;
                border-radius: 8px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        
        label = QLabel("Reserved for Dynamic Loss Chart Integration")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #ADB5BD; font-size: 14px; font-weight: bold;")
        
        frame_layout.addWidget(label)
        layout.addWidget(self.frame)


class PredictionEvolutionStrip(QWidget):
    """实时预测演进预览横向展示"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Live Prediction Evolution")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)
        
        # Use a horizontal scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background-color: transparent;")
        
        self.container = QWidget()
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 8, 0, 8)
        self.container_layout.setSpacing(16)
        
        self._add_placeholder()
            
        self.container_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        # Internal state to keep track of received iters
        self.iter_groups = {} # dict[int, list of dicts]

    def _add_placeholder(self):
        # 展示 Input | GT | Pred 这个样板占位
        for title_text in ["Input Image", "Ground Truth", "Latest Prediction"]:
            group = QVBoxLayout()
            group.setSpacing(4)
            
            box = QLabel(f"[{title_text} Area]")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setMinimumSize(120, 120)
            box.setStyleSheet("background-color: #E9ECEF; border-radius: 4px; color: #6C757D;")
            
            txt = QLabel(title_text)
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt.setStyleSheet("color: #868E96; font-size: 11px;")
            
            group.addWidget(box, stretch=1)
            group.addWidget(txt, stretch=0)
            self.container_layout.addLayout(group)

    def _clear_layout(self):
        while self.container_layout.count() > 1:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # clear nested layouts
                self._clear_nested_layout(item.layout())

    def _clear_nested_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_nested_layout(item.layout())
        layout.deleteLater()

    def _get_colorized_pixmap(self, mask_path: str, size: int=120) -> QPixmap:
        if not mask_path or not os.path.exists(mask_path):
            return QPixmap()
        try:
            # Use imdecode to robustly handle paths containing Chinese/unicode characters
            mask_data = np.fromfile(mask_path, dtype=np.uint8)
            mask = cv2.imdecode(mask_data, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                return QPixmap()
            colors = [
                [0,0,0], [0,200,0], [0,128,0], [128,128,0], [0,0,128], [128,0,128], [0,128,128], [128,128,128],
                [64,0,0], [192,0,0], [64,128,0], [192,128,0], [64,0,128], [192,0,128], [64,128,128], [192,128,128],
                [0,64,0], [128,64,0], [0,192,0], [128,192,0], [0,64,128]
            ]
            h, w = mask.shape
            color_mask = np.zeros((h, w, 3), dtype=np.uint8)
            for i, color in enumerate(colors):
                color_mask[mask == i] = color
            color_mask[mask > len(colors)-1] = [255, 255, 255]
            # Convert BGR to RGB using cv2 to guarantee a C-contiguous array
            color_mask = cv2.cvtColor(color_mask, cv2.COLOR_BGR2RGB)
            
            # Use .copy() to ensure the memory belongs to QImage, preventing silent garbage collection crashes/corruption
            qimg = QImage(color_mask.data, w, h, w*3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(qimg)
            return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        except Exception as e:
            print(f"Failed to colorize pic: {e}")
            return QPixmap()

    def update_live_predictions(self, data: dict):
        """
        data 格式: {"type": "live_prediction", "iter": 4000, "img": "...", "gt": "...", "pred": "..."}
        """
        iter_num = data.get('iter', 0)
        if iter_num not in self.iter_groups:
            self.iter_groups[iter_num] = []
        
        # 只保留最新的 3 个 iter 以免 UI 过硬
        if len(self.iter_groups) > 3:
            oldest_iter = min(self.iter_groups.keys())
            if iter_num != oldest_iter:
                del self.iter_groups[oldest_iter]

        self.iter_groups[iter_num].append(data)
        self._render_predictions()

    def _render_predictions(self):
        self._clear_layout()
        
        if not self.iter_groups:
            self._add_placeholder()
            self.container_layout.addStretch()
            return
            
        # 按 Iter 降序排序展示（最新的在左边）
        sorted_iters = sorted(self.iter_groups.keys(), reverse=True)
        
        for iter_num in sorted_iters:
            samples = self.iter_groups[iter_num]
            if not samples:
                continue
            
            # 一个 Iter 块
            iter_widget = QWidget()
            iter_widget.setStyleSheet("""
                QWidget {
                    background-color: #F8F9FA;
                    border: 1px solid #DEE2E6;
                    border-radius: 8px;
                }
            """)
            iter_layout = QVBoxLayout(iter_widget)
            iter_layout.setContentsMargins(12, 12, 12, 12)
            
            header = QLabel(f"Iteration: {iter_num}")
            header.setStyleSheet("font-weight: bold; color: #212529; border: none; background: transparent;")
            iter_layout.addWidget(header)
            
            # Use first sample only per iter group (hook now sends 1 per iter)
            s = samples[0]
            IMG_SIZE = 140
            MASK_SIZE = 140

            panels_layout = QHBoxLayout()
            panels_layout.setSpacing(8)

            def _make_panel(title_text, lbl_widget):
                col = QVBoxLayout()
                col.setSpacing(4)
                ttl = QLabel(title_text)
                ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ttl.setStyleSheet("color: #6C757D; font-size: 10px; border: none; background: transparent;")
                col.addWidget(lbl_widget)
                col.addWidget(ttl)
                return col

            # --- Input Image ---
            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setFixedSize(IMG_SIZE, IMG_SIZE)
            img_lbl.setStyleSheet("background-color: #000; border-radius: 6px; border: none;")
            img_path = s.get('img', '')
            if os.path.exists(img_path):
                img_data = np.fromfile(img_path, dtype=np.uint8)
                img_cv = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
                if img_cv is not None:
                    img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
                    h, w, _ = img_rgb.shape
                    qimg = QImage(img_rgb.data, w, h, w*3, QImage.Format_RGB888).copy()
                    pix = QPixmap.fromImage(qimg).scaled(IMG_SIZE, IMG_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_lbl.setPixmap(pix)
                else:
                    img_lbl.setText("Img")
            else:
                img_lbl.setText("No Img")

            # --- Ground Truth ---
            gt_lbl = QLabel()
            gt_lbl.setFixedSize(MASK_SIZE, MASK_SIZE)
            gt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gt_lbl.setStyleSheet("background-color: #1A1A2E; border-radius: 6px; border: none;")
            gt_pix = self._get_colorized_pixmap(s.get('gt', ''), MASK_SIZE)
            if not gt_pix.isNull():
                gt_lbl.setPixmap(gt_pix)
            else:
                gt_lbl.setText("GT")

            # --- Prediction ---
            pred_lbl = QLabel()
            pred_lbl.setFixedSize(MASK_SIZE, MASK_SIZE)
            pred_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pred_lbl.setStyleSheet("background-color: #1A1A2E; border-radius: 6px; border: 2px solid #20C997;")
            pred_pix = self._get_colorized_pixmap(s.get('pred', ''), MASK_SIZE)
            if not pred_pix.isNull():
                pred_lbl.setPixmap(pred_pix)
            else:
                pred_lbl.setText("Pred")

            panels_layout.addLayout(_make_panel("Input", img_lbl))
            panels_layout.addLayout(_make_panel("GT", gt_lbl))
            panels_layout.addLayout(_make_panel("Pred ✓", pred_lbl))

            iter_layout.addLayout(panels_layout)
            self.container_layout.insertWidget(self.container_layout.count() - 1, iter_widget)


class ResourceMonitorWidget(QWidget):
    """硬件与进度资源监控"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # GPU / ETA 卡片模块样式
        card_style = """
            QFrame {
                background-color: #F8F9FA;
                border: 1px solid #E9ECEF;
                border-radius: 6px;
            }
        """
        
        def make_metric(title, value):
            frame = QFrame()
            frame.setStyleSheet(card_style)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(12, 12, 12, 12)
            
            tl = QLabel(title)
            tl.setStyleSheet("color: #6C757D; font-size: 11px; font-weight: bold;")
            
            vl = QLabel(value)
            vl.setStyleSheet("color: #212529; font-size: 18px; font-weight: bold;")
            
            fl.addWidget(tl)
            fl.addWidget(vl)
            return frame
            
        layout.addWidget(make_metric("GPU Memory", "10.2 / 12.0 GB"))
        layout.addWidget(make_metric("GPU Util", "85%"))
        layout.addWidget(make_metric("ETA", "2h 34m remaining"), stretch=1)


class TrainingExecutionDashboard(QWidget):
    """训练执行时中心监控大屏"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        header = QLabel("Live Training Center")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #212529;")
        layout.addWidget(header)
        
        # 实时训练曲线图表：优先使用真实的 MetricsPlotWidget，降级到占位符
        if _HAS_METRICS_PLOT:
            self.metrics_plot = MetricsPlotWidget()
        else:
            self.metrics_plot = LossCurvePlaceholder()
        
        self.prediction_strip = PredictionEvolutionStrip()
        self.resource_monitor = ResourceMonitorWidget()
        
        layout.addWidget(self.metrics_plot, stretch=3)
        layout.addWidget(self.prediction_strip, stretch=2)
        layout.addWidget(self.resource_monitor, stretch=1)


class TaskConfigDashboard(QStackedWidget):
    """
    中心主仪表盘容器，根据状态切换蓝图视角或监控视角。
    采用 Ignored SizePolicy，自适应填充但不强制改变外层比例空间。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 强调尺寸约束：绝不能撑大中心区域
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(300, 200) # 与 SmartCanvas 和 GridView 的最小尺寸保持一致以稳定 Splitter
        
        # 整体面板强制使用纯净浅色背景
        self.setStyleSheet("""
            TaskConfigDashboard {
                background-color: #FFFFFF;
            }
            QWidget {
                background-color: transparent;
            }
        """)
        
        self.blueprint_view = TaskConfigBlueprintWidget()
        self.training_view = TrainingExecutionDashboard()
        
        self.addWidget(self.blueprint_view)
        self.addWidget(self.training_view)
        
        self.setCurrentWidget(self.blueprint_view)
        
    def switch_to_blueprint(self):
        """Switch back to Task Config"""
        self.setCurrentWidget(self.blueprint_view)
        
    def switch_to_training(self):
        """Switch to Training Live Monitor"""
        self.setCurrentWidget(self.training_view)
        
    def update_config_params(self, params: dict):
        """暴露给外部的配置更新接口"""
        self.blueprint_view.update_blueprint(params)
