# -*- coding: utf-8 -*-
"""
权重选择组件 (Weight Selection Widget)

提供预训练权重的管理机制：
1. 公共预训练 (如 ImageNet、COCO 等对应 Backbone 的默认权重)
2. 自有遥感权重 (.pth)

这是从原 ModelSelectionWidget 中拆分出来的独立组件。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QTabWidget, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QLabel,
    QSizePolicy, QProgressBar, QMessageBox
)
from PySide6.QtCore import Signal, QThread
from ui.widgets.model_selection_widget import PRETRAINED_MODELS
from ui.widgets.wheel_guard import install_wheel_guard

# 预训练权重下载地址表 {(backbone_display_name, dataset): url}
WEIGHT_URL_MAP = {
    ('MiT-B0', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b0_20220624-7e0fe6dd.pth',
    ('MiT-B1', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b1_20220624-02e5a6a1.pth',
    ('MiT-B2', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b2_20220624-66e8bf70.pth',
    ('MiT-B5', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b5_20220624-658746d9.pth',
    ('ResNet-50', 'ImageNet-1K'): 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth',
    ('ResNet-101', 'ImageNet-1K'): 'https://download.openmmlab.com/pretrain/third_party/resnet101_v1c-e67eebb6.pth',
    ('Swin-Tiny', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth',
    ('Swin-Base', 'ImageNet-22K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_base_patch4_window12_384_20220317-55b0104a.pth',
}


class WeightDownloadWorker(QThread):
    """后台下载预训练权重文件。"""
    progress = Signal(int)       # 0~100
    finished_ok = Signal(str)    # 下载完成，携带本地路径
    failed = Signal(str)         # 下载失败，携带错误信息

    def __init__(self, url: str, save_path: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._save_path = save_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            import urllib.request
            os.makedirs(os.path.dirname(self._save_path), exist_ok=True)

            # 先获取文件大小
            with urllib.request.urlopen(self._url, timeout=10) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                chunk = 8192
                with open(self._save_path, 'wb') as f:
                    while not self._cancelled:
                        data = resp.read(chunk)
                        if not data:
                            break
                        f.write(data)
                        downloaded += len(data)
                        if total > 0:
                            self.progress.emit(int(downloaded * 100 / total))

            if self._cancelled:
                if os.path.exists(self._save_path):
                    os.remove(self._save_path)
                self.failed.emit("已取消下载")
            else:
                self.progress.emit(100)
                self.finished_ok.emit(self._save_path)
        except Exception as e:
            self.failed.emit(str(e))


class WeightSelectionWidget(QWidget):
    """
    权重选择组件

    布局：
    - QTabWidget：
        - Tab 1 "公共预训练": ImageNet/COCO 预训练复选框 + 模型下拉列表 + 下载按钮
        - Tab 2 "自有遥感权重": 文件选择器选择 .pth 文件

    Signals:
        config_changed(): 任何配置项变更时触发
    """

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_backbone = ''
        self._download_worker = None
        self._setup_ui()
        self._connect_signals()
        self.combo_pretrained_model.clear()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.tab_pretrained = QTabWidget()
        self.tab_pretrained.setMaximumHeight(160)

        # --- Tab 1: 公共预训练 ---
        tab_public = QWidget()
        tab_public_layout = QVBoxLayout(tab_public)
        tab_public_layout.setContentsMargins(6, 6, 6, 6)
        tab_public_layout.setSpacing(4)

        self.check_use_pretrained = QCheckBox("使用预训练权重 (Use Pretrained)")
        self.check_use_pretrained.setChecked(True)
        tab_public_layout.addWidget(self.check_use_pretrained)

        pretrained_row = QHBoxLayout()
        pretrained_row.addWidget(QLabel("预训练模型:"))
        self.combo_pretrained_model = QComboBox()
        self.combo_pretrained_model.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        pretrained_row.addWidget(self.combo_pretrained_model)
        self.btn_download = QPushButton("⬇ 下载")
        self.btn_download.setFixedWidth(64)
        self.btn_download.setToolTip("下载所选预训练权重到 pretrain/ 目录")
        pretrained_row.addWidget(self.btn_download)
        tab_public_layout.addLayout(pretrained_row)

        self.progress_download = QProgressBar()
        self.progress_download.setVisible(False)
        self.progress_download.setMaximumHeight(12)
        tab_public_layout.addWidget(self.progress_download)

        self.tab_pretrained.addTab(tab_public, "公共预训练 (Public)")

        # --- Tab 2: 自有遥感权重 ---
        tab_custom = QWidget()
        tab_custom_layout = QVBoxLayout(tab_custom)
        tab_custom_layout.setContentsMargins(6, 6, 6, 6)
        tab_custom_layout.setSpacing(4)

        self.check_use_custom_weight = QCheckBox("使用自有权重 (Custom .pth)")
        tab_custom_layout.addWidget(self.check_use_custom_weight)

        weight_row = QHBoxLayout()
        self.line_custom_weight = QLineEdit()
        self.line_custom_weight.setPlaceholderText("选择 .pth 权重文件...")
        self.line_custom_weight.setReadOnly(True)
        self.btn_browse_weight = QPushButton("浏览...")
        weight_row.addWidget(self.line_custom_weight)
        weight_row.addWidget(self.btn_browse_weight)
        tab_custom_layout.addLayout(weight_row)

        self.tab_pretrained.addTab(tab_custom, "自有业务权重 (Custom)")
        layout.addWidget(self.tab_pretrained)

        # UI-09：阻止鼠标悬停时滚轮误改 ComboBox 的选项
        install_wheel_guard(self)

    def _connect_signals(self):
        self.check_use_pretrained.toggled.connect(self._on_pretrained_toggled)
        self.btn_browse_weight.clicked.connect(self._on_browse_weight)
        self.btn_download.clicked.connect(self._on_download_weight)
        self.combo_pretrained_model.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.check_use_custom_weight.toggled.connect(lambda: self.config_changed.emit())

    def update_backbone(self, backbone_name: str):
        """外部调用：当 Backbone 改变时，更新可用的预训练模型列表并扫描本地缓存。"""
        self._current_backbone = backbone_name
        self.combo_pretrained_model.clear()
        models = PRETRAINED_MODELS.get(backbone_name, [])
        self.combo_pretrained_model.addItems(models)
        self._scan_local_pretrain(backbone_name)
        self.config_changed.emit()

    def _scan_local_pretrain(self, backbone_name: str):
        """扫描 pretrain/ 目录，若找到匹配当前 backbone 的权重则自动填入自有权重路径。"""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        pretrain_dir = os.path.join(project_root, 'pretrain')
        if not os.path.isdir(pretrain_dir):
            return
        # 用 backbone 关键词模糊匹配（如 mit_b0、resnet50）
        keyword = backbone_name.lower().replace('-', '_').replace(' ', '_')
        for fname in os.listdir(pretrain_dir):
            if keyword in fname.lower() and fname.endswith('.pth'):
                full_path = os.path.join(pretrain_dir, fname)
                self.line_custom_weight.setText(full_path)
                self.check_use_custom_weight.setChecked(True)
                self.config_changed.emit()
                return

    def _on_pretrained_toggled(self, checked):
        self.combo_pretrained_model.setEnabled(checked)
        self.config_changed.emit()

    def _on_browse_weight(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择权重文件", "",
            "PyTorch 权重 (*.pth);;所有文件 (*)"
        )
        if path:
            self.line_custom_weight.setText(path)
            self.check_use_custom_weight.setChecked(True)
            self.config_changed.emit()

    def _on_download_weight(self):
        """下载当前选中的公共预训练权重到 pretrain/ 目录。"""
        dataset = self.combo_pretrained_model.currentText()
        url = WEIGHT_URL_MAP.get((self._current_backbone, dataset))
        if not url:
            QMessageBox.information(self, "下载权重",
                f"暂无 {self._current_backbone} / {dataset} 的自动下载链接。\n"
                "请前往 OpenMMLab 官方仓库手动下载后放入 pretrain/ 目录。")
            return

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        fname = url.split('/')[-1]
        save_path = os.path.join(project_root, 'pretrain', fname)

        if os.path.exists(save_path):
            QMessageBox.information(self, "下载权重", f"权重文件已存在：\n{save_path}")
            self.line_custom_weight.setText(save_path)
            self.check_use_custom_weight.setChecked(True)
            self.tab_pretrained.setCurrentIndex(1)
            return

        self.btn_download.setEnabled(False)
        self.progress_download.setValue(0)
        self.progress_download.setVisible(True)

        self._download_worker = WeightDownloadWorker(url, save_path, self)
        self._download_worker.progress.connect(self.progress_download.setValue)
        self._download_worker.finished_ok.connect(self._on_download_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.start()

    def _on_download_finished(self, path: str):
        self.progress_download.setVisible(False)
        self.btn_download.setEnabled(True)
        self.line_custom_weight.setText(path)
        self.check_use_custom_weight.setChecked(True)
        self.tab_pretrained.setCurrentIndex(1)
        self.config_changed.emit()

    def _on_download_failed(self, error: str):
        self.progress_download.setVisible(False)
        self.btn_download.setEnabled(True)
        QMessageBox.warning(self, "下载失败", f"权重下载失败：\n{error}")

    def get_params(self) -> dict:
        return {
            'use_pretrained': self.check_use_pretrained.isChecked(),
            'pretrained_model': self.combo_pretrained_model.currentText(),
            'use_custom_weight': self.check_use_custom_weight.isChecked(),
            'custom_weight_path': self.line_custom_weight.text(),
        }

    def set_params(self, params: dict):
        if not isinstance(params, dict):
            return

        if 'use_pretrained' in params:
            self.check_use_pretrained.setChecked(bool(params.get('use_pretrained')))

        pretrained_model = params.get('pretrained_model')
        if pretrained_model:
            idx = self.combo_pretrained_model.findText(str(pretrained_model))
            if idx >= 0:
                self.combo_pretrained_model.setCurrentIndex(idx)
            else:
                self.combo_pretrained_model.addItem(str(pretrained_model))
                self.combo_pretrained_model.setCurrentText(str(pretrained_model))

        custom_weight_path = params.get('custom_weight_path')
        if custom_weight_path:
            self.line_custom_weight.setText(str(custom_weight_path))

        if 'use_custom_weight' in params:
            self.check_use_custom_weight.setChecked(bool(params.get('use_custom_weight')))
