# -*- coding: utf-8 -*-
"""
推理可视化面板 (Inference Visualization Panel)
负责管理推理配置、模型加载、推理执行和结果导出
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QRadioButton, QCheckBox, QButtonGroup, QFrame, QScrollArea,
    QProgressBar, QFileDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer
import os
import numpy as np


class InferencePanel(QWidget):
    """推理可视化面板"""
    
    # 信号定义
    model_loaded = Signal(dict)  # 模型加载完成信号
    inference_started = Signal()  # 推理开始信号
    inference_finished = Signal(dict)  # 推理完成信号
    inference_error = Signal(str)  # 推理错误信号
    log_message = Signal(str)  # 日志消息信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.inference_model = None
        self.last_inference_result = None  # 保存最后一次推理结果
        self._setup_ui()
        self._connect_signals()
        self._init_inference_config()
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 模型加载区
        self._create_model_config_group(layout)
        
        # 推理策略区
        self._create_inference_strategy_group(layout)
        
        # 执行与导出区
        self._create_action_export_group(layout)
        
        # 推理结果显示区
        self._create_inference_result_group(layout)
        
        # 添加弹性空间
        layout.addStretch()
    
    def _create_model_config_group(self, parent_layout):
        """创建模型加载区"""
        self.groupBox_modelConfig = QGroupBox("模型加载区 (Model Configuration)")
        form_layout = QFormLayout(self.groupBox_modelConfig)
        
        # 配置文件
        self.label_configFile = QLabel("配置文件:")
        config_layout = QHBoxLayout()
        self.lineEdit_configFile = QLineEdit()
        self.lineEdit_configFile.setPlaceholderText("选择 MMSeg 配置文件 (.py)")
        self.pushButton_browseConfig = QPushButton("浏览...")
        config_layout.addWidget(self.lineEdit_configFile)
        config_layout.addWidget(self.pushButton_browseConfig)
        form_layout.addRow(self.label_configFile, config_layout)
        
        # 模型名称（自动解析）
        self.label_modelName = QLabel("模型名称:")
        self.label_modelNameValue = QLabel("未加载配置")
        self.label_modelNameValue.setStyleSheet("color: #888; font-style: italic;")
        form_layout.addRow(self.label_modelName, self.label_modelNameValue)
        
        # 权重文件
        self.label_checkpointFile = QLabel("权重文件:")
        checkpoint_layout = QHBoxLayout()
        self.lineEdit_checkpointFile = QLineEdit()
        self.lineEdit_checkpointFile.setPlaceholderText("选择模型权重文件 (.pth)")
        self.pushButton_browseCheckpoint = QPushButton("浏览...")
        checkpoint_layout.addWidget(self.lineEdit_checkpointFile)
        checkpoint_layout.addWidget(self.pushButton_browseCheckpoint)
        form_layout.addRow(self.label_checkpointFile, checkpoint_layout)
        
        # 计算设备
        self.label_device = QLabel("计算设备:")
        self.comboBox_device = QComboBox()
        self.comboBox_device.addItems(["Auto", "CUDA:0", "CPU"])
        form_layout.addRow(self.label_device, self.comboBox_device)
        
        # 加载按钮和状态
        load_layout = QHBoxLayout()
        self.pushButton_loadModel = QPushButton("加载模型")
        self.label_modelStatus = QLabel("未加载")
        load_layout.addWidget(self.pushButton_loadModel)
        load_layout.addWidget(self.label_modelStatus)
        load_layout.addStretch()
        form_layout.addRow("", load_layout)
        
        # 类别图例
        self.label_classesLegend = QLabel("类别图例:")
        self.scrollArea_classesLegend = QScrollArea()
        self.scrollArea_classesLegend.setWidgetResizable(True)
        self.scrollArea_classesLegend.setMaximumHeight(150)
        self.scrollArea_classesLegend.setVisible(False)
        
        self.scrollAreaWidgetContents_classes = QWidget()
        self.verticalLayout_classes = QVBoxLayout(self.scrollAreaWidgetContents_classes)
        self.verticalLayout_classes.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout_classes.setSpacing(3)
        self.scrollArea_classesLegend.setWidget(self.scrollAreaWidgetContents_classes)
        form_layout.addRow(self.label_classesLegend, self.scrollArea_classesLegend)
        
        parent_layout.addWidget(self.groupBox_modelConfig)

    def _create_inference_strategy_group(self, parent_layout):
        """创建推理策略区"""
        self.groupBox_inferenceStrategy = QGroupBox("推理策略区 (Inference Strategy)")
        form_layout = QFormLayout(self.groupBox_inferenceStrategy)
        
        # 推理模式选择（单图/批量）
        self.label_inferenceMode = QLabel("推理模式:")
        mode_layout = QHBoxLayout()
        self.radioButton_singleImage = QRadioButton("单图推理")
        self.radioButton_singleImage.setChecked(True)
        self.radioButton_batchInference = QRadioButton("批量推理")
        mode_layout.addWidget(self.radioButton_singleImage)
        mode_layout.addWidget(self.radioButton_batchInference)
        mode_layout.addStretch()
        self.buttonGroup_inferenceMode = QButtonGroup(self)
        self.buttonGroup_inferenceMode.addButton(self.radioButton_singleImage)
        self.buttonGroup_inferenceMode.addButton(self.radioButton_batchInference)
        form_layout.addRow(self.label_inferenceMode, mode_layout)
        
        # 批量目录选择
        self.label_batchDir = QLabel("批量目录:")
        batch_layout = QHBoxLayout()
        self.lineEdit_batchDir = QLineEdit()
        self.lineEdit_batchDir.setEnabled(False)
        self.pushButton_browseBatchDir = QPushButton("浏览...")
        self.pushButton_browseBatchDir.setEnabled(False)
        batch_layout.addWidget(self.lineEdit_batchDir)
        batch_layout.addWidget(self.pushButton_browseBatchDir)
        form_layout.addRow(self.label_batchDir, batch_layout)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line1)
        
        # 推理策略模式选择（滑窗/全图缩放）
        self.label_strategyMode = QLabel("策略模式:")
        strategy_layout = QHBoxLayout()
        self.radioButton_slidingWindow = QRadioButton("滑窗推理 (Sliding Window)")
        self.radioButton_slidingWindow.setChecked(True)
        self.radioButton_resize = QRadioButton("全图缩放 (Resize)")
        strategy_layout.addWidget(self.radioButton_slidingWindow)
        strategy_layout.addWidget(self.radioButton_resize)
        strategy_layout.addStretch()
        self.buttonGroup_strategyMode = QButtonGroup(self)
        self.buttonGroup_strategyMode.addButton(self.radioButton_slidingWindow)
        self.buttonGroup_strategyMode.addButton(self.radioButton_resize)
        form_layout.addRow(self.label_strategyMode, strategy_layout)
        
        # 全图缩放说明
        self.label_resizeNote = QLabel("提示：全图缩放仅用于小尺寸图像的快速预览")
        self.label_resizeNote.setWordWrap(True)
        self.label_resizeNote.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        form_layout.addRow("", self.label_resizeNote)
        
        # 滑窗参数 - 窗口大小
        self.label_cropSize = QLabel("窗口大小 (Crop Size):")
        self.spinBox_cropSize = QSpinBox()
        self.spinBox_cropSize.setMinimum(256)
        self.spinBox_cropSize.setMaximum(2048)
        self.spinBox_cropSize.setSingleStep(64)
        self.spinBox_cropSize.setValue(1024)
        form_layout.addRow(self.label_cropSize, self.spinBox_cropSize)
        
        # 滑窗参数 - 步长
        self.label_stride = QLabel("步长 (Stride):")
        stride_layout = QHBoxLayout()
        self.spinBox_stride = QSpinBox()
        self.spinBox_stride.setMinimum(64)
        self.spinBox_stride.setMaximum(2048)
        self.spinBox_stride.setSingleStep(64)
        self.spinBox_stride.setValue(512)
        self.label_strideHint = QLabel("建议为窗口大小的50%-75%")
        self.label_strideHint.setStyleSheet("color: #888; font-size: 10px;")
        stride_layout.addWidget(self.spinBox_stride)
        stride_layout.addWidget(self.label_strideHint)
        stride_layout.addStretch()
        form_layout.addRow(self.label_stride, stride_layout)
        
        # 滑窗参数 - 批大小
        self.label_batchSize = QLabel("批大小 (Batch Size):")
        batch_size_layout = QHBoxLayout()
        self.spinBox_batchSize = QSpinBox()
        self.spinBox_batchSize.setMinimum(1)
        self.spinBox_batchSize.setMaximum(32)
        self.spinBox_batchSize.setValue(1)
        self.label_batchSizeHint = QLabel("根据GPU显存调整")
        self.label_batchSizeHint.setStyleSheet("color: #888; font-size: 10px;")
        batch_size_layout.addWidget(self.spinBox_batchSize)
        batch_size_layout.addWidget(self.label_batchSizeHint)
        batch_size_layout.addStretch()
        form_layout.addRow(self.label_batchSize, batch_size_layout)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line2)
        
        # TTA增强选项
        self.checkBox_enableTTA = QCheckBox("启用多尺度翻转增强 (Enable TTA)")
        form_layout.addRow("", self.checkBox_enableTTA)
        
        # 分隔线
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line3)
        
        # 置信度阈值
        self.label_confThreshold = QLabel("置信度阈值:")
        self.doubleSpinBox_confThreshold = QDoubleSpinBox()
        self.doubleSpinBox_confThreshold.setMinimum(0.0)
        self.doubleSpinBox_confThreshold.setMaximum(1.0)
        self.doubleSpinBox_confThreshold.setSingleStep(0.05)
        self.doubleSpinBox_confThreshold.setValue(0.5)
        form_layout.addRow(self.label_confThreshold, self.doubleSpinBox_confThreshold)
        
        parent_layout.addWidget(self.groupBox_inferenceStrategy)
    
    def _create_action_export_group(self, parent_layout):
        """创建执行与导出区"""
        self.groupBox_actionExport = QGroupBox("执行与导出 (Action & Export)")
        form_layout = QFormLayout(self.groupBox_actionExport)
        
        # 自定义预测脚本
        self.label_customScript = QLabel("自定义预测脚本:")
        custom_script_layout = QHBoxLayout()
        self.lineEdit_customScript = QLineEdit()
        self.lineEdit_customScript.setPlaceholderText("选择自定义预测脚本 (.py) - 可选")
        self.pushButton_browseCustomScript = QPushButton("浏览...")
        custom_script_layout.addWidget(self.lineEdit_customScript)
        custom_script_layout.addWidget(self.pushButton_browseCustomScript)
        form_layout.addRow(self.label_customScript, custom_script_layout)
        
        # 运行推理按钮
        self.pushButton_runInference = QPushButton("运行推理 (Run Inference)")
        form_layout.addRow(self.pushButton_runInference)
        
        # 批量推理按钮
        self.pushButton_batchInference = QPushButton("批量推理 (Batch Inference)")
        form_layout.addRow(self.pushButton_batchInference)
        
        # 进度条
        self.label_inferenceProgress = QLabel("进度:")
        self.progressBar_inference = QProgressBar()
        self.progressBar_inference.setValue(0)
        form_layout.addRow(self.label_inferenceProgress, self.progressBar_inference)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)
        
        # 导出格式
        self.label_exportFormat = QLabel("导出格式:")
        export_format_layout = QHBoxLayout()
        self.checkBox_exportPNG = QCheckBox("PNG")
        self.checkBox_exportPNG.setChecked(True)
        self.checkBox_exportNumpy = QCheckBox("NumPy (.npy)")
        self.checkBox_exportJSON = QCheckBox("JSON")
        export_format_layout.addWidget(self.checkBox_exportPNG)
        export_format_layout.addWidget(self.checkBox_exportNumpy)
        export_format_layout.addWidget(self.checkBox_exportJSON)
        export_format_layout.addStretch()
        form_layout.addRow(self.label_exportFormat, export_format_layout)
        
        # 导出目录
        self.label_exportDir = QLabel("导出目录:")
        export_dir_layout = QHBoxLayout()
        self.lineEdit_exportDir = QLineEdit()
        self.pushButton_browseExportDir = QPushButton("浏览...")
        export_dir_layout.addWidget(self.lineEdit_exportDir)
        export_dir_layout.addWidget(self.pushButton_browseExportDir)
        form_layout.addRow(self.label_exportDir, export_dir_layout)
        
        # 导出结果按钮
        self.pushButton_exportResults = QPushButton("导出结果")
        form_layout.addRow(self.pushButton_exportResults)
        
        parent_layout.addWidget(self.groupBox_actionExport)
    
    def _create_inference_result_group(self, parent_layout):
        """创建推理结果显示区"""
        self.groupBox_inferenceResult = QGroupBox("推理结果 (Inference Result)")
        layout = QVBoxLayout(self.groupBox_inferenceResult)
        
        self.label_inferenceResult = QLabel("暂无推理结果\n\n请加载模型并运行推理，结果将显示在此处。")
        self.label_inferenceResult.setWordWrap(True)
        self.label_inferenceResult.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label_inferenceResult.setMinimumHeight(100)
        layout.addWidget(self.label_inferenceResult)
        
        parent_layout.addWidget(self.groupBox_inferenceResult)

    def _connect_signals(self):
        """连接信号"""
        # 模型加载区
        self.pushButton_browseConfig.clicked.connect(self._browse_config_file)
        self.pushButton_browseCheckpoint.clicked.connect(self._browse_checkpoint_file)
        self.lineEdit_configFile.textChanged.connect(self._on_config_file_changed)
        self.pushButton_loadModel.clicked.connect(self._load_inference_model)
        
        # 推理模式切换
        self.radioButton_batchInference.toggled.connect(self._on_inference_mode_changed)
        
        # 策略模式切换
        self.radioButton_slidingWindow.toggled.connect(self._on_strategy_mode_changed)
        
        # 批量目录浏览
        self.pushButton_browseBatchDir.clicked.connect(self._browse_batch_dir)
        
        # 自定义脚本浏览
        self.pushButton_browseCustomScript.clicked.connect(self._browse_custom_script)
        
        # 导出目录浏览
        self.pushButton_browseExportDir.clicked.connect(self._browse_export_dir)
        
        # 推理执行
        self.pushButton_runInference.clicked.connect(self._run_inference)
        self.pushButton_batchInference.clicked.connect(self._run_batch_inference)
        
        # 导出结果
        self.pushButton_exportResults.clicked.connect(self._export_results)
    
    def _init_inference_config(self):
        """初始化推理配置"""
        cuda_available = self._check_cuda_available()
        
        if cuda_available:
            self.comboBox_device.setCurrentIndex(0)  # Auto
            self._emit_log("🎮 [推理配置] CUDA 可用，默认设备: Auto")
        else:
            self.comboBox_device.setCurrentIndex(2)  # CPU
            # 禁用 CUDA:0 选项
            model = self.comboBox_device.model()
            item = model.item(1)
            if item:
                item.setEnabled(False)
                item.setToolTip("CUDA 不可用")
            self._emit_log("⚠️  [推理配置] CUDA 不可用，默认设备: CPU")
    
    def _check_cuda_available(self) -> bool:
        """检测 CUDA 是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
        except Exception:
            return False
    
    def _emit_log(self, message: str):
        """发送日志消息"""
        self.log_message.emit(message)
        print(message)
    
    def _browse_config_file(self):
        """浏览并选择MMSeg配置文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 MMSegmentation 配置文件",
            "",
            "Python Files (*.py);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        self.lineEdit_configFile.setText(file_path)
        
        if not self._validate_config_file(file_path):
            return
        
        # 尝试解析模型名称
        try:
            config_info = self._parse_config_file(file_path)
            model_name = config_info.get('model_name', '未知模型')
            
            self.label_modelNameValue.setText(model_name)
            self.label_modelNameValue.setStyleSheet("color: #000; font-style: normal; font-weight: bold;")
            
            self._emit_log(f"✅ [推理配置] 已加载配置文件: {os.path.basename(file_path)}")
            self._emit_log(f"   📝 模型名称: {model_name}")
            
            # 智能推荐权重文件
            self._suggest_checkpoint_file(file_path, model_name)
            
        except Exception as e:
            self.label_modelNameValue.setText("解析失败")
            self.label_modelNameValue.setStyleSheet("color: #f00; font-style: italic;")
            self._emit_log(f"❌ [推理配置] 配置文件解析失败: {e}")
    
    def _validate_config_file(self, file_path: str) -> bool:
        """验证配置文件格式"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            required_keywords = ['model', 'dict']
            has_keywords = any(keyword in content for keyword in required_keywords)
            
            if not has_keywords:
                QMessageBox.warning(
                    self,
                    "配置文件格式错误",
                    "所选文件可能不是有效的 MMSegmentation 配置文件。\n\n"
                    "有效的配置文件应包含 'model' 定义。"
                )
                return False
            
            return True
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "文件读取错误",
                f"无法读取配置文件。\n\n错误信息: {e}"
            )
            return False
    
    def _parse_config_file(self, file_path: str) -> dict:
        """解析配置文件获取模型信息 - 使用增强解析器"""
        try:
            # 使用增强的配置解析器
            from core.config_parser import ConfigParser
            parser = ConfigParser()
            
            # 解析配置文件
            classes, palette = parser.parse_config_file(file_path)
            model_name = parser.extract_model_name(file_path)
            model_type = parser.extract_model_type(file_path)
            
            # 构建配置信息
            config_info = {
                'model_name': model_name or os.path.splitext(os.path.basename(file_path))[0],
                'model_type': model_type,
                'classes': classes,
                'palette': palette
            }
            
            return config_info
            
        except Exception as e:
            # 优雅降级 - 不影响模型加载
            self._emit_log(f"⚠️  配置解析警告: {e}")
            return {
                'model_name': os.path.splitext(os.path.basename(file_path))[0],
                'model_type': None,
                'classes': None,
                'palette': None
            }
    
    def _suggest_checkpoint_file(self, config_path: str, model_name: str):
        """智能推荐权重文件"""
        config_dir = os.path.dirname(config_path)
        
        search_dirs = [
            config_dir,
            os.path.join(config_dir, 'checkpoints'),
            os.path.join(config_dir, '..', 'checkpoints'),
            os.path.join(config_dir, 'work_dirs'),
        ]
        
        found_checkpoints = []
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            
            try:
                for file in os.listdir(search_dir):
                    if file.endswith(('.pth', '.pt')):
                        file_lower = file.lower()
                        model_lower = model_name.lower().replace('-', '').replace(' ', '')
                        
                        if model_lower in file_lower.replace('-', '').replace('_', ''):
                            found_checkpoints.append(os.path.join(search_dir, file))
            except:
                continue
        
        if found_checkpoints:
            latest_checkpoint = max(found_checkpoints, key=os.path.getmtime)
            
            reply = QMessageBox.question(
                self,
                "发现匹配的权重文件",
                f"找到与模型 '{model_name}' 匹配的权重文件：\n\n"
                f"{os.path.basename(latest_checkpoint)}\n\n"
                f"是否使用此权重文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.lineEdit_checkpointFile.setText(latest_checkpoint)
                self._emit_log(f"💡 [推理配置] 自动选择权重文件: {os.path.basename(latest_checkpoint)}")
    
    def _browse_checkpoint_file(self):
        """浏览并选择模型权重文件"""
        start_dir = ""
        config_path = self.lineEdit_configFile.text()
        if config_path and os.path.exists(config_path):
            start_dir = os.path.dirname(config_path)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择模型权重文件",
            start_dir,
            "PyTorch Checkpoint (*.pth *.pt);;All Files (*.*)"
        )
        
        if file_path:
            self.lineEdit_checkpointFile.setText(file_path)
            
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
            
            self._emit_log(f"✅ [推理配置] 已选择权重文件: {os.path.basename(file_path)}")
            self._emit_log(f"   📦 文件大小: {size_mb:.2f} MB")
    
    def _on_config_file_changed(self, text):
        """配置文件路径变化时触发"""
        if not text:
            self.label_modelNameValue.setText("未加载配置")
            self.label_modelNameValue.setStyleSheet("color: #888; font-style: italic;")
    
    def _on_inference_mode_changed(self, checked):
        """推理模式切换"""
        self.lineEdit_batchDir.setEnabled(checked)
        self.pushButton_browseBatchDir.setEnabled(checked)
    
    def _on_strategy_mode_changed(self, checked):
        """策略模式切换"""
        self.spinBox_cropSize.setEnabled(checked)
        self.spinBox_stride.setEnabled(checked)
        self.spinBox_batchSize.setEnabled(checked)
    
    def _browse_batch_dir(self):
        """浏览批量推理目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择批量推理图像目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.lineEdit_batchDir.setText(dir_path)
    
    def _browse_custom_script(self):
        """浏览自定义预测脚本"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择自定义预测脚本",
            "",
            "Python Files (*.py);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        self.lineEdit_customScript.setText(file_path)
        
        # 验证脚本文件
        if not os.path.exists(file_path):
            self._emit_log(f"⚠️  脚本文件不存在: {file_path}")
            return
        
        self._emit_log(f"✅ [推理配置] 已选择自定义脚本: {os.path.basename(file_path)}")
        
        # 可选：验证脚本是否包含必要的函数
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否包含常见的推理函数
            has_inference_func = any(keyword in content for keyword in ['def inference', 'def predict', 'def run'])
            
            if has_inference_func:
                self._emit_log(f"   ✓ 脚本包含推理函数")
            else:
                self._emit_log(f"   ⚠️  脚本可能不包含推理函数，请确认")
        
        except Exception as e:
            self._emit_log(f"⚠️  脚本验证失败: {e}")
    
    def _browse_export_dir(self):
        """浏览导出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择导出目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.lineEdit_exportDir.setText(dir_path)

    def _load_inference_model(self):
        """加载推理模型"""
        config_path = self.lineEdit_configFile.text().strip()
        checkpoint_path = self.lineEdit_checkpointFile.text().strip()
        
        if not config_path:
            self._emit_log("⚠️  请先选择配置文件")
            QMessageBox.warning(self, "缺少配置文件", "请先选择 MMSegmentation 配置文件。")
            return
        
        if not checkpoint_path:
            self._emit_log("⚠️  请先选择权重文件")
            QMessageBox.warning(self, "缺少权重文件", "请先选择模型权重文件。")
            return
        
        if not os.path.exists(config_path):
            self._emit_log(f"❌ 配置文件不存在: {config_path}")
            QMessageBox.critical(self, "配置文件不存在", f"配置文件不存在:\n{config_path}")
            return
        
        if not os.path.exists(checkpoint_path):
            self._emit_log(f"❌ 权重文件不存在: {checkpoint_path}")
            QMessageBox.critical(self, "权重文件不存在", f"权重文件不存在:\n{checkpoint_path}")
            return
        
        device_text = self.comboBox_device.currentText()
        device_map = {"Auto": "cuda:0", "CUDA:0": "cuda:0", "CPU": "cpu"}
        device = device_map.get(device_text, "cpu")
        
        if device_text == "Auto" and not self._check_cuda_available():
            device = "cpu"
        
        self.pushButton_loadModel.setEnabled(False)
        self._emit_log("🔄 正在加载模型...")
        
        QApplication.processEvents()
        QTimer.singleShot(100, lambda: self._do_load_inference_model(config_path, checkpoint_path, device))
    
    def _do_load_inference_model(self, config_path: str, checkpoint_path: str, device: str):
        """实际执行模型加载 - 增强版本"""
        try:
            # 解析配置文件 - 使用健壮解析器
            config_info = self._parse_config_file_robust(config_path)
            
            # 即使配置解析失败，也继续模型加载
            if config_info.get('classes') is None:
                self._emit_log("⚠️  未找到类别信息，将使用默认设置")
            
            # 保存模型信息（实际项目中应使用 MMSegmentation API 加载真实模型）
            self.inference_model = {
                'config': config_path,
                'checkpoint': checkpoint_path,
                'device': device,
                'classes': config_info.get('classes'),
                'palette': config_info.get('palette'),
                'model_name': config_info.get('model_name', 'Unknown Model')
            }
            
            self.pushButton_loadModel.setEnabled(True)
            self.label_modelStatus.setText("模型已就绪")
            self.label_modelStatus.setStyleSheet("color: #28a745; font-weight: bold;")
            
            # 显示类别图例 - 安全版本
            try:
                self._display_classes_legend_safe(config_info.get('classes'), config_info.get('palette'))
            except Exception as legend_error:
                self._emit_log(f"⚠️  类别图例显示警告: {legend_error}")
            
            self._emit_log("✅ 模型已就绪 (Model Ready)")
            self.model_loaded.emit(self.inference_model)
            
        except Exception as e:
            self._handle_model_loading_error(e)
    
    def _parse_config_file_robust(self, file_path: str) -> dict:
        """健壮的配置文件解析"""
        try:
            from core.config_parser import ConfigParser
            parser = ConfigParser()
            classes, palette = parser.parse_config_file(file_path)
            model_name = parser.extract_model_name(file_path)
            model_type = parser.extract_model_type(file_path)
            
            return {
                'classes': classes,
                'palette': palette,
                'model_name': model_name,
                'model_type': model_type
            }
        except Exception as e:
            # 记录警告但不抛出异常
            self._emit_log(f"⚠️  配置解析失败: {e}")
            return {
                'classes': None, 
                'palette': None, 
                'model_name': os.path.splitext(os.path.basename(file_path))[0],
                'model_type': None
            }

    def _display_classes_legend_safe(self, classes, palette):
        """安全的类别图例显示"""
        try:
            self._display_classes_legend(classes, palette)
        except Exception as e:
            self._emit_log(f"⚠️  类别图例显示失败: {e}")
            # 隐藏图例区域但不影响其他功能
            try:
                self.scrollArea_classesLegend.setVisible(False)
            except:
                pass
    
    def _handle_model_loading_error(self, error: Exception):
        """处理模型加载错误"""
        self.pushButton_loadModel.setEnabled(True)
        self.label_modelStatus.setText("加载失败")
        self.label_modelStatus.setStyleSheet("color: #dc3545; font-weight: bold;")
        
        import traceback
        error_details = traceback.format_exc()
        self._emit_log(f"❌ 模型加载失败: {error}")
        self._emit_log(f"详细错误:\n{error_details}")
        
        QMessageBox.critical(self, "模型加载失败", f"模型加载过程中发生错误。\n\n错误信息:\n{str(error)}")
    
    def _display_classes_legend(self, classes, palette):
        """显示类别图例"""
        try:
            layout = self.verticalLayout_classes
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            if classes is None:
                classes = []
            if palette is None:
                palette = []
            
            if not classes or not palette:
                self.scrollArea_classesLegend.setVisible(False)
                self._emit_log("⚠️  配置文件中未找到 CLASSES 或 PALETTE 信息")
                return
            
            self.scrollArea_classesLegend.setVisible(True)
            
            for idx, class_name in enumerate(classes):
                try:
                    if idx < len(palette):
                        color = palette[idx]
                        if isinstance(color, (list, tuple)) and len(color) >= 3:
                            r, g, b = int(color[0]), int(color[1]), int(color[2])
                        else:
                            r, g, b = 128, 128, 128
                    else:
                        r, g, b = 128, 128, 128
                    
                    class_label = QLabel(self.scrollAreaWidgetContents_classes)
                    class_label.setObjectName(f"label_class_{idx}")
                    class_label.setText(f"  {str(class_name)}")
                    class_label.setStyleSheet(
                        f"background-color: rgb({r}, {g}, {b}); "
                        f"color: {'white' if (r + g + b) < 384 else 'black'}; "
                        f"padding: 3px 8px; "
                        f"border-radius: 3px; "
                        f"font-size: 11px;"
                    )
                    
                    layout.addWidget(class_label)
                except Exception as label_error:
                    self._emit_log(f"⚠️  创建类别标签 {idx} 失败: {label_error}")
                    continue
            
            layout.addStretch()
            
            if classes:
                self._emit_log(f"📊 已加载 {len(classes)} 个类别")
            
        except Exception as e:
            self._emit_log(f"⚠️  类别图例显示失败: {e}")
            try:
                self.scrollArea_classesLegend.setVisible(False)
            except:
                pass
    
    def _run_inference(self):
        """运行单图推理"""
        # 1. 检查模型是否已加载
        if not self.inference_model:
            self._emit_log("⚠️  模型未加载，无法执行推理")
            QMessageBox.warning(self, "模型未加载", "请先加载推理模型。")
            return
        
        # 2. 弹出文件选择对话框选择图片
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要推理的图像",
            "",
            "Image Files (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;All Files (*.*)"
        )
        
        if not image_path:
            self._emit_log("⚠️  未选择图像文件")
            return
        
        # 3. 读取选择的图片（验证）
        if not os.path.exists(image_path):
            self._emit_log(f"❌ 图像文件不存在: {image_path}")
            QMessageBox.critical(self, "文件不存在", f"图像文件不存在:\n{image_path}")
            return
        
        try:
            from PIL import Image
            
            # 针对大尺寸遥感影像，提高PIL的像素限制
            # 默认限制约为178MB像素，这里提高到10GB像素
            Image.MAX_IMAGE_PIXELS = 10000000000
            
            img = Image.open(image_path)
            img_width, img_height = img.size
            img_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            
            self._emit_log(f"📷 已加载图像: {os.path.basename(image_path)}")
            self._emit_log(f"   尺寸: {img_width} x {img_height} ({img_width * img_height / 1000000:.1f}M 像素)")
            self._emit_log(f"   文件大小: {img_size_mb:.2f} MB")
            
            # 对于超大图像给出警告和建议
            if img_width * img_height > 100000000:  # 超过1亿像素
                self._emit_log(f"⚠️  检测到超大尺寸图像，建议使用滑窗推理")
                
                # 如果当前选择的是全图缩放，提示用户切换
                if self.radioButton_resize.isChecked():
                    reply = QMessageBox.question(
                        self,
                        "超大图像警告",
                        f"检测到超大尺寸图像 ({img_width} x {img_height})。\n\n"
                        f"当前选择的是'全图缩放'模式，可能导致内存不足。\n"
                        f"建议切换到'滑窗推理'模式。\n\n"
                        f"是否继续使用全图缩放模式？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.No:
                        self._emit_log("⚠️  用户取消推理")
                        return
            
        except Exception as e:
            self._emit_log(f"❌ 图像读取失败: {e}")
            QMessageBox.critical(self, "图像读取失败", f"无法读取图像文件。\n\n错误信息:\n{str(e)}")
            return
        
        # 发送推理开始信号
        self.inference_started.emit()
        self._emit_log("🚀 开始单图推理...")
        
        # 禁用推理按钮，防止重复点击
        self.pushButton_runInference.setEnabled(False)
        self.progressBar_inference.setValue(0)
        
        # 获取推理配置
        strategy = 'resize' if self.radioButton_resize.isChecked() else 'sliding_window'
        inference_params = {
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'batch_size': self.spinBox_batchSize.value(),
            'enable_tta': self.checkBox_enableTTA.isChecked(),
            'conf_threshold': self.doubleSpinBox_confThreshold.value()
        }
        
        self._emit_log(f"   策略模式: {strategy}")
        if strategy == 'sliding_window':
            self._emit_log(f"   窗口大小: {inference_params['crop_size']}")
            self._emit_log(f"   步长: {inference_params['stride']}")
            self._emit_log(f"   批大小: {inference_params['batch_size']}")
        self._emit_log(f"   TTA增强: {'启用' if inference_params['enable_tta'] else '禁用'}")
        
        # 使用 QTimer 异步执行推理，避免阻塞UI
        QApplication.processEvents()
        QTimer.singleShot(100, lambda: self._do_run_inference(image_path, strategy, inference_params))
    
    def _do_run_inference(self, image_path: str, strategy: str, inference_params: dict):
        """实际执行推理任务"""
        try:
            self._emit_log("🔄 开始执行推理...")
            self._emit_log(f"   图像路径: {image_path}")
            self._emit_log(f"   推理策略: {strategy}")
            
            # 4. 根据策略模式调用不同推理方法
            from core.inference_engine import InferenceEngine
            
            # 创建推理引擎
            self._emit_log("🔧 创建推理引擎...")
            engine = InferenceEngine(self.inference_model)
            
            # 更新进度条
            self.progressBar_inference.setValue(30)
            QApplication.processEvents()
            
            # 执行推理
            self._emit_log(f"⚙️  执行{strategy}推理...")
            if strategy == 'sliding_window':
                result = engine.sliding_window_inference(
                    image_path,
                    crop_size=inference_params['crop_size'],
                    stride=inference_params['stride'],
                    batch_size=inference_params['batch_size'],
                    enable_tta=inference_params['enable_tta']
                )
            else:  # resize
                result = engine.resize_inference(
                    image_path,
                    enable_tta=inference_params['enable_tta']
                )
            
            self._emit_log(f"📊 推理结果: success={result.get('success', False)}")
            
            # 更新进度条
            self.progressBar_inference.setValue(80)
            QApplication.processEvents()
            
            # 5. 处理预测结果
            if result.get('success', False):
                self._emit_log("✅ 推理成功，处理结果...")
                self._handle_inference_success(image_path, result, inference_params)
            else:
                error_msg = result.get('error', '未知错误')
                self._emit_log(f"❌ 推理失败: {error_msg}")
                self._handle_inference_error(error_msg)
            
            # 完成进度条
            self.progressBar_inference.setValue(100)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self._emit_log(f"❌ 推理异常: {e}")
            self._emit_log(f"详细错误:\n{error_details}")
            self._handle_inference_error(f"{str(e)}\n\n详细信息:\n{error_details}")
        
        finally:
            # 重新启用推理按钮
            self.pushButton_runInference.setEnabled(True)
    
    def _handle_inference_success(self, image_path: str, result: dict, inference_params: dict):
        """处理推理成功的结果"""
        try:
            # 提取结果信息
            mask = result.get('mask')
            image_shape = result.get('image_shape', (0, 0))
            strategy = result.get('strategy', 'unknown')
            params = result.get('params', {})
            
            # 构建结果显示文本
            result_text = f"✅ 推理完成！\n\n"
            result_text += f"⚠️  注意：当前使用模拟推理（未集成MMSegmentation）\n\n"
            result_text += f"📷 图像: {os.path.basename(image_path)}\n"
            result_text += f"📐 尺寸: {image_shape[1]} x {image_shape[0]}\n"
            result_text += f"🎯 策略: {strategy}\n\n"
            
            if strategy == 'sliding_window':
                result_text += f"窗口参数:\n"
                result_text += f"  • 窗口大小: {params.get('crop_size', 'N/A')}\n"
                result_text += f"  • 步长: {params.get('stride', 'N/A')}\n"
                result_text += f"  • 批大小: {params.get('batch_size', 'N/A')}\n"
                result_text += f"  • 窗口总数: {params.get('total_windows', 'N/A')}\n"
            
            result_text += f"\n推理配置:\n"
            result_text += f"  • TTA增强: {'启用' if params.get('enable_tta', False) else '禁用'}\n"
            result_text += f"  • 置信度阈值: {inference_params.get('conf_threshold', 0.5)}\n"
            
            # 统计类别分布
            unique_classes = []  # 初始化变量
            total_pixels = image_shape[0] * image_shape[1]
            
            if mask is not None:
                unique_classes = np.unique(mask)
                result_text += f"\n检测到的类别: {len(unique_classes)} 个\n"
                
                classes = result.get('classes', [])
                if classes:
                    result_text += f"\n类别分布:\n"
                    for cls_id in unique_classes[:10]:  # 最多显示10个类别
                        if cls_id < len(classes):
                            cls_name = classes[cls_id]
                            pixel_count = np.sum(mask == cls_id)
                            percentage = (pixel_count / mask.size) * 100
                            result_text += f"  • {cls_name}: {percentage:.2f}%\n"
            else:
                # 超大图像，未生成完整掩码
                result_text += f"\n💡 超大图像处理模式:\n"
                result_text += f"  • 总像素: {total_pixels:,} ({total_pixels/1000000:.1f}M)\n"
                result_text += f"  • 为节省内存，未生成完整预测掩码\n"
                result_text += f"  • 推理流程已验证成功\n"
                result_text += f"  • 集成MMSegmentation后将生成真实结果\n"
            
            # 更新结果显示
            self.label_inferenceResult.setText(result_text)
            
            # 保存推理结果供导出使用
            self.last_inference_result = {
                'image_path': image_path,
                'mask': mask,
                'result': result,
                'params': inference_params
            }
            
            # 发送推理完成信号
            self.inference_finished.emit(result)
            
            self._emit_log("✅ 推理完成")
            if mask is not None:
                self._emit_log(f"   检测到 {len(unique_classes)} 个类别")
            else:
                self._emit_log(f"   超大图像模式：未生成完整掩码（正常）")
            
            # 提示用户可以导出结果
            QMessageBox.information(
                self,
                "推理完成",
                f"推理已成功完成！\n\n"
                f"图像: {os.path.basename(image_path)}\n"
                f"策略: {strategy}\n\n"
                f"您可以在下方查看详细结果，或点击'导出结果'保存推理结果。"
            )
            
        except Exception as e:
            self._emit_log(f"⚠️  结果处理警告: {e}")
            self.label_inferenceResult.setText(f"推理完成，但结果处理出现问题:\n{str(e)}")
    
    def _handle_inference_error(self, error_msg: str):
        """处理推理错误"""
        self.progressBar_inference.setValue(0)
        
        error_text = f"❌ 推理失败\n\n错误信息:\n{error_msg}"
        self.label_inferenceResult.setText(error_text)
        
        self._emit_log(f"❌ 推理失败: {error_msg}")
        
        # 发送错误信号
        self.inference_error.emit(error_msg)
        
        QMessageBox.critical(
            self,
            "推理失败",
            f"推理过程中发生错误。\n\n错误信息:\n{error_msg}"
        )
    
    def _run_batch_inference(self):
        """运行批量推理"""
        if not self.inference_model:
            QMessageBox.warning(self, "模型未加载", "请先加载推理模型。")
            return
        
        batch_dir = self.lineEdit_batchDir.text().strip()
        if not batch_dir or not os.path.isdir(batch_dir):
            QMessageBox.warning(self, "批量目录无效", "请选择有效的批量推理图像目录。")
            return
        
        self.inference_started.emit()
        self._emit_log(f"🚀 开始批量推理: {batch_dir}")
        
        # TODO: 实现实际的批量推理逻辑
        self.label_inferenceResult.setText("批量推理功能待实现...\n\n请在实际项目中集成 MMSegmentation 推理 API。")
    
    def _export_results(self):
        """导出推理结果"""
        export_dir = self.lineEdit_exportDir.text().strip()
        if not export_dir:
            QMessageBox.warning(self, "导出目录未设置", "请先选择导出目录。")
            return
        
        self._emit_log(f"📤 导出结果到: {export_dir}")
        
        # TODO: 实现实际的导出逻辑
        QMessageBox.information(self, "导出功能", "导出功能待实现...")
    
    def get_inference_config(self) -> dict:
        """获取当前推理配置"""
        return {
            'config_file': self.lineEdit_configFile.text(),
            'checkpoint_file': self.lineEdit_checkpointFile.text(),
            'device': self.comboBox_device.currentText(),
            'custom_script': self.lineEdit_customScript.text(),
            'inference_mode': 'batch' if self.radioButton_batchInference.isChecked() else 'single',
            'batch_dir': self.lineEdit_batchDir.text(),
            'strategy_mode': 'resize' if self.radioButton_resize.isChecked() else 'sliding_window',
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'batch_size': self.spinBox_batchSize.value(),
            'enable_tta': self.checkBox_enableTTA.isChecked(),
            'conf_threshold': self.doubleSpinBox_confThreshold.value(),
            'export_formats': {
                'png': self.checkBox_exportPNG.isChecked(),
                'numpy': self.checkBox_exportNumpy.isChecked(),
                'json': self.checkBox_exportJSON.isChecked()
            },
            'export_dir': self.lineEdit_exportDir.text()
        }
    
    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self.inference_model is not None
