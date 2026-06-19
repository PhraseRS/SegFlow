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
from ui.widgets.wheel_guard import install_wheel_guard
from config.backbone_registry import PRETRAINED_MODELS, WEIGHT_URL_MAP


class WeightDownloadWorker(QThread):
    """后台下载预训练权重文件。"""
    progress = Signal(int)       # 0~100
    finished_ok = Signal(str)    # 下载完成，携带本地路径
    failed = Signal(str)         # Download failed，携带ErrorInfo

    def __init__(self, url: str, save_path: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._save_path = save_path
        self._cancelled = False
        self._paused = False

    def cancel(self):
        self._cancelled = True

    def pause(self):
        self._paused = True
        
    def resume(self):
        self._paused = False

    def run(self):
        try:
            import urllib.request
            import time
            os.makedirs(os.path.dirname(self._save_path), exist_ok=True)

            # 先获取文件大小
            with urllib.request.urlopen(self._url, timeout=10) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                chunk = 8192
                with open(self._save_path, 'wb') as f:
                    while not self._cancelled:
                        if self._paused:
                            time.sleep(0.1)
                            continue
                            
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
        - Tab 2 "自有遥感权重": 文件选择器Select .pth 文件

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

        self.check_use_pretrained = QCheckBox("Use Pretrained Weights")
        self.check_use_pretrained.setChecked(True)
        tab_public_layout.addWidget(self.check_use_pretrained)

        pretrained_row = QHBoxLayout()
        pretrained_row.addWidget(QLabel("Pretrained Model:"))
        self.combo_pretrained_model = QComboBox()
        self.combo_pretrained_model.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        pretrained_row.addWidget(self.combo_pretrained_model)
        self.btn_download = QPushButton("⬇ Download")
        self.btn_download.setMinimumWidth(85)
        self.btn_download.setToolTip("下载所选预训练权重到 pretrain/ 目录")
        pretrained_row.addWidget(self.btn_download)
        
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.setMinimumWidth(80)
        self.btn_pause.setVisible(False)
        pretrained_row.addWidget(self.btn_pause)
        
        self.btn_cancel = QPushButton("⏹ Cancel")
        self.btn_cancel.setMinimumWidth(80)
        self.btn_cancel.setVisible(False)
        pretrained_row.addWidget(self.btn_cancel)
        
        tab_public_layout.addLayout(pretrained_row)

        self.progress_download = QProgressBar()
        self.progress_download.setVisible(False)
        self.progress_download.setMaximumHeight(12)
        tab_public_layout.addWidget(self.progress_download)

        self.tab_pretrained.addTab(tab_public, "Public Pretrained")

        # --- Tab 2: 自有遥感权重 ---
        tab_custom = QWidget()
        tab_custom_layout = QVBoxLayout(tab_custom)
        tab_custom_layout.setContentsMargins(6, 6, 6, 6)
        tab_custom_layout.setSpacing(4)

        self.check_use_custom_weight = QCheckBox("Use Custom Weights (.pth)")
        tab_custom_layout.addWidget(self.check_use_custom_weight)

        weight_row = QHBoxLayout()
        self.line_custom_weight = QLineEdit()
        self.line_custom_weight.setPlaceholderText("Select .pth 权重文件...")
        self.line_custom_weight.setReadOnly(True)
        self.btn_browse_weight = QPushButton("Browse...")
        weight_row.addWidget(self.line_custom_weight)
        weight_row.addWidget(self.btn_browse_weight)
        tab_custom_layout.addLayout(weight_row)

        self.lbl_local_hint = QLabel("")
        self.lbl_local_hint.setStyleSheet("color: #E65100; font-size: 11px;")
        tab_custom_layout.addWidget(self.lbl_local_hint)

        self.tab_pretrained.addTab(tab_custom, "Custom Weights")
        layout.addWidget(self.tab_pretrained)

        # UI-09：阻止鼠标悬停时滚轮误改 ComboBox 的选项
        install_wheel_guard(self)

    def _connect_signals(self):
        self.check_use_pretrained.toggled.connect(self._on_pretrained_toggled)
        self.btn_browse_weight.clicked.connect(self._on_browse_weight)
        self.btn_download.clicked.connect(self._on_download_weight)
        self.btn_pause.clicked.connect(self._on_pause_resume_download)
        self.btn_cancel.clicked.connect(self._on_cancel_download)
        self.combo_pretrained_model.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.check_use_custom_weight.toggled.connect(lambda: self.config_changed.emit())

    def update_backbone(self, backbone_name: str):
        """外部调用：当 Backbone 改变时，更新可用的预训练模型列表并扫描本地缓存。"""
        self._current_backbone = backbone_name
        self.combo_pretrained_model.clear()
        models = PRETRAINED_MODELS.get(backbone_name, [])
        self.combo_pretrained_model.addItems(models)
        self.lbl_local_hint.setText("")
        self._scan_local_pretrain(backbone_name)
        self.config_changed.emit()

    def _scan_local_pretrain(self, backbone_name: str):
        """扫描 pretrain/ 目录，若找到匹配当前 backbone 的权重则填入自有权重路径，但不自动勾选。"""
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
                self.lbl_local_hint.setText("⚡ Matched weights found locally, check to use")
                # 移除强制 setChecked(True) 避免覆盖用户意图
                self.config_changed.emit()
                return

    def _on_pretrained_toggled(self, checked):
        self.combo_pretrained_model.setEnabled(checked)
        self.config_changed.emit()

    def _on_browse_weight(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Weight File", "",
            "PyTorch Weights (*.pth);;All Files (*)"
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
            QMessageBox.information(self, "Download Weights",
                f"No {self._current_backbone} / {dataset} 的自动下载链接。\n"
                "请前往 OpenMMLab 官方仓库手动下载后放入 pretrain/ 目录。")
            return

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        fname = url.split('/')[-1]
        save_path = os.path.join(project_root, 'pretrain', fname)

        if os.path.exists(save_path):
            QMessageBox.information(self, "Download Weights", f"Weight file already exists:\n{save_path}")
            self.line_custom_weight.setText(save_path)
            self.check_use_custom_weight.setChecked(True)
            self.tab_pretrained.setCurrentIndex(1)
            return

        self.btn_download.setVisible(False)
        self.btn_pause.setVisible(True)
        self.btn_cancel.setVisible(True)
        self.btn_pause.setText("⏸ Pause")
        self.progress_download.setValue(0)
        self.progress_download.setVisible(True)

        self._download_worker = WeightDownloadWorker(url, save_path, self)
        self._download_worker.progress.connect(self.progress_download.setValue)
        self._download_worker.finished_ok.connect(self._on_download_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.start()

    def _reset_download_ui(self):
        self.btn_download.setVisible(True)
        self.btn_pause.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.progress_download.setVisible(False)
        self.progress_download.setValue(0)
        self.btn_pause.setText("⏸ Pause")

    def _on_pause_resume_download(self):
        if not self._download_worker:
            return
        if self._download_worker._paused:
            self._download_worker.resume()
            self.btn_pause.setText("⏸ Pause")
        else:
            self._download_worker.pause()
            self.btn_pause.setText("▶ Resume")

    def _on_cancel_download(self):
        if self._download_worker:
            self._download_worker.cancel()
        self._reset_download_ui()

    def _on_download_finished(self, path: str):
        self._reset_download_ui()
        self.line_custom_weight.setText(path)
        self.check_use_custom_weight.setChecked(True)
        self.tab_pretrained.setCurrentIndex(1)
        self.config_changed.emit()

    def _on_download_failed(self, error: str):
        self._reset_download_ui()
        if "已取消下载" not in error:
            QMessageBox.warning(self, "Download failed", f"权重Download failed：\n{error}")

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
