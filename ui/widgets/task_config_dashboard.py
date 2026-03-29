# -*- coding: utf-8 -*-
"""
TaskConfigDashboard - 任务配置与训练执行中心仪表盘 (Visual Dashboard)
提供配置管线蓝图、数据增强预览、健康度打分，以及训练过程监控界面的占位。

严格遵循系统浅色主题规范与布局尺寸约束 (自适应填充但不强制撑大)。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QSizePolicy, QProgressBar, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPixmap


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
    """样本增强实时预览横向滚动带"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("实时增强预览 (Live Augmentation Preview)")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)
        
        # 这里用作占位，展示对比视图卡片
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        
        container = QWidget()
        self.container_layout = QHBoxLayout(container)
        self.container_layout.setContentsMargins(0, 8, 0, 8)
        self.container_layout.setSpacing(16)
        
        # 添加 3 个占位对
        self._create_placeholders()
            
        self.container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _create_placeholders(self):
        """清空并重新创建 3 个占位符"""
        # 清除现有
        while self.container_layout.count() > 1:  # 保留结尾的 stretch
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        for i in range(3):
            pair_widget = QWidget()
            pair_layout = QVBoxLayout(pair_widget)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            
            img_pair = QLabel(f"[暂无样本 {i+1}]")
            img_pair.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_pair.setMinimumSize(256, 128)
            img_pair.setStyleSheet("""
                background-color: #E9ECEF; 
                border: 1px dashed #CED4DA; 
                border-radius: 4px;
                color: #6C757D;
            """)
            
            desc = QLabel(f"等待样本载入...")
            desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc.setStyleSheet("color: #868E96; font-size: 11px;")
            
            pair_layout.addWidget(img_pair)
            pair_layout.addWidget(desc)
            
            self.container_layout.insertWidget(self.container_layout.count() - 1, pair_widget)

    def update_previews(self, preview_data):
        """
        接入真实样本数据
        :param preview_data: list of dicts [{'img_path': str, 'lbl_path': str, 'name': str}]
        """
        # 清除现有控件（保留结尾 stretch）
        while self.container_layout.count() > 1:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not preview_data:
            self._create_placeholders()
            return

        for data in preview_data:
            pair_widget = QWidget()
            pair_layout = QVBoxLayout(pair_widget)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            
            # 显示区域
            imgs_container = QWidget()
            imgs_layout = QHBoxLayout(imgs_container)
            imgs_layout.setContentsMargins(0, 0, 0, 0)
            
            # 读取图片
            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet("background-color: #E9ECEF; border-radius: 4px;")
            img_lbl.setMinimumSize(128, 128)
            if data['img_path']:
                pix = QPixmap(data['img_path']).scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                img_lbl.setPixmap(pix)
            else:
                img_lbl.setText("无图片")
                
            # 读取标签
            lbl_lbl = QLabel()
            lbl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_lbl.setStyleSheet("background-color: #E9ECEF; border-radius: 4px;")
            lbl_lbl.setMinimumSize(128, 128)
            if data['lbl_path']:
                pix_gt = QPixmap(data['lbl_path']).scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                lbl_lbl.setPixmap(pix_gt)
            else:
                lbl_lbl.setText("无标签")
                
            imgs_layout.addWidget(img_lbl)
            imgs_layout.addWidget(QLabel("➡️"))
            imgs_layout.addWidget(lbl_lbl)
            
            # 描述文字
            desc = QLabel(f"样本: {data['name']}")
            desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc.setStyleSheet("color: #495057; font-size: 11px; font-weight: bold;")
            
            pair_layout.addWidget(imgs_container)
            pair_layout.addWidget(desc)
            
            self.container_layout.insertWidget(self.container_layout.count() - 1, pair_widget)


class ConfigHealthBar(QWidget):
    """配置健康度水平打分条"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("配置健康度 (Configuration Health Score)")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)
        
        # 进度条布局
        bar_layout = QHBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v 分")  # 显示具体分数
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
                background-color: #20C997; /* 默认绿色 */
                border-radius: 11px;
            }
        """)
        bar_layout.addWidget(self.progress_bar, stretch=1)
        
        layout.addLayout(bar_layout)
        
        # 徽章布局
        pills_layout = QHBoxLayout()
        pills_layout.setSpacing(8)
        
        self.pills = {
            "vram": self._create_pill("预估显存: -- GB", "#F1F3F5", "#495057"),
            "data": self._create_pill("数据集: 未就绪", "#F1F3F5", "#495057"),
            "params": self._create_pill("参数: 待配置", "#F1F3F5", "#495057")
        }
        
        for p in self.pills.values():
            pills_layout.addWidget(p)
        pills_layout.addStretch()
        
        layout.addLayout(pills_layout)
        
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


class TaskConfigBlueprintWidget(QWidget):
    """任务配置视图中心总控面板"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(24)
        
        # 标题区
        header = QLabel("任务配置蓝图 (Task Configuration Dashboard)")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #212529;")
        layout.addWidget(header)
        
        # 三大核心区块
        self.blueprint = PipelineBlueprintWidget()
        self.preview_strip = AugmentationPreviewStrip()
        self.health_bar = ConfigHealthBar()
        
        layout.addWidget(self.blueprint, stretch=1)
        layout.addWidget(self.preview_strip, stretch=2)
        layout.addWidget(self.health_bar, stretch=1)
        
        # 默认更新初始状态
        self.update_blueprint({})

    def update_blueprint(self, params: dict):
        """
        根据完整的参数字典更新蓝图各节点与健康度。
        params 整合了 HyperparamTabsWidget / ModelSelectionWidget 以及数据集信息。
        """
        # ---- Dataset 节点 ----
        dataset_samples = params.get("dataset_samples", 0)
        data_root = params.get("data_root", "")
        dataset_ready = bool(dataset_samples > 0 or data_root)
        if dataset_ready:
            label = f"{dataset_samples} 样本" if dataset_samples else "已加载"
            self.blueprint.nodes["dataset"].set_active(True, label)
        else:
            self.blueprint.nodes["dataset"].set_active(False, "未加载数据集")

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

        # ---- Model 节点 ----
        model_info = params.get("model", "")
        backbone = params.get("backbone", "")
        in_ch = params.get("in_channels", 3)
        if model_info:
            model_label = f"{model_info} | {in_ch}ch"
        elif backbone:
            model_label = f"{backbone} | {in_ch}ch"
        else:
            model_label = "待选择"
        self.blueprint.nodes["model"].set_active(bool(model_info or backbone), model_label)

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
        """4维度加权健康度评分（满分100）并更新 Pills"""
        score = 0

        # 1. 数据集就绪（25分）
        if dataset_ready:
            score += 25
            ds = params.get('dataset_samples', 0)
            self.pills_status_update("data", f"✅ 数据: {ds or ''}已就绪", "#D4EDDA", "#155724")
        else:
            self.pills_status_update("data", "⚠ 数据: 未加载", "#FFF3CD", "#856404")

        # 2. 模型参数已选（25分）
        if params.get("model") or params.get("backbone"):
            score += 25
            self.pills_status_update("params", "✅ 参数: 已配置", "#D4EDDA", "#155724")
        else:
            self.pills_status_update("params", "⚠ 参数: 待配置", "#FFF3CD", "#856404")

        # 3. 批大小与显存估算（25分）
        batch_size = params.get("batch_size", 2)
        crop_size = params.get("crop_size", 512)
        in_ch = params.get("in_channels", 3)
        estimated_vram_gb = round((crop_size ** 2 * in_ch * 4 * batch_size * 4) / 1e9, 1)
        if estimated_vram_gb <= 8:
            score += 25
            self.pills_status_update("vram", f"✅ 显存预估: ~{estimated_vram_gb}GB", "#D4EDDA", "#155724")
        elif estimated_vram_gb <= 16:
            score += 15
            self.pills_status_update("vram", f"⚠ 显存预估: ~{estimated_vram_gb}GB", "#FFF3CD", "#856404")
        else:
            self.pills_status_update("vram", f"❌ 显存: ~{estimated_vram_gb}GB OOM风险!", "#F8D7DA", "#721C24")

        # 4. 关键增强选项（25分）
        if params.get("aug_random_flip", False) or params.get("aug_photo_distortion", False):
            score += 25

        # 更新进度条（含动态颜色）
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
            pill.setStyleSheet(f"background-color: {bg}; color: {fg}; padding: 4px 10px; border-radius: 10px; font-size: 11px; font-weight: bold;")


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
        
        label = QLabel("预留：训练曲线图表展示区\n(Reserved for Dynamic Loss Chart Integration)")
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
        
        title = QLabel("实时预测演进 (Live Prediction Evolution)")
        title.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(title)
        
        # 展示 Input | GT | Pred 结构
        container_layout = QHBoxLayout()
        container_layout.setContentsMargins(0, 8, 0, 8)
        container_layout.setSpacing(16)
        
        for title_text in ["Input Image", "Ground Truth", "Latest Prediction"]:
            group = QVBoxLayout()
            group.setSpacing(4)
            
            box = QLabel(f"[{title_text} Area]")
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setMinimumSize(160, 160)
            box.setStyleSheet("background-color: #E9ECEF; border-radius: 4px; color: #6C757D;")
            
            txt = QLabel(title_text)
            txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt.setStyleSheet("color: #868E96; font-size: 11px;")
            
            group.addWidget(box, stretch=1)
            group.addWidget(txt, stretch=0)
            container_layout.addLayout(group)
            
        layout.addLayout(container_layout)


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
        
        header = QLabel("训练执行监控 (Live Training Center)")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #212529;")
        layout.addWidget(header)
        
        self.loss_placeholder = LossCurvePlaceholder()
        self.prediction_strip = PredictionEvolutionStrip()
        self.resource_monitor = ResourceMonitorWidget()
        
        layout.addWidget(self.loss_placeholder, stretch=2)
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
        """切回任务配置面板"""
        self.setCurrentWidget(self.blueprint_view)
        
    def switch_to_training(self):
        """切换到训练执行监视大屏"""
        self.setCurrentWidget(self.training_view)
        
    def update_config_params(self, params: dict):
        """暴露给外部的配置更新接口"""
        self.blueprint_view.update_blueprint(params)
