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
from PySide6.QtCore import Qt, Signal, QTimer, QThread
import os
import numpy as np


# =============================================================================
# Worker Thread Class
# =============================================================================

class InferenceWorker(QThread):
    """
    后台推理工作线程
    用于在后台执行耗时的推理任务，避免阻塞主界面
    """
    # 信号定义
    finished = Signal(str, dict, dict)  # (image_path, result, params)
    error = Signal(str)                 # (error_msg)
    log = Signal(str)                   # (log_msg)
    progress = Signal(int)              # (progress_value: 0-100)
    cancelled = Signal()                # 取消完成信号
    
    def __init__(self, inference_model: dict, image_path: str, strategy: str, inference_params: dict, output_path: str = None):
        super().__init__()
        self.inference_model = inference_model
        self.image_path = image_path
        self.strategy = strategy
        self.inference_params = inference_params
        self.output_path = output_path
        
        # 推理引擎引用 (用于取消)
        self._engine = None
        self._cancel_requested = False
    
    def request_cancel(self):
        """请求取消推理"""
        self._cancel_requested = True
        if self._engine:
            self._engine.request_cancel()
        self.log.emit("🛑 已发送取消请求...")
    
    def _on_engine_progress(self, current, total):
        """推理引擎进度回调"""
        # 将进度映射到10-90的范围
        progress_value = int(10 + (current / total) * 80)
        self.progress.emit(progress_value)
        
    def run(self):
        try:
            self.log.emit("🔄 开始执行后台推理...")
            self.log.emit(f"   图像路径: {self.image_path}")
            self.log.emit(f"   推理策略: {self.strategy}")
            
            # 导入推理引擎 (延迟导入避免循环依赖)
            from core.inference_engine import InferenceEngine
            
            # 创建推理引擎
            self.log.emit("🔧 初始化推理引擎...")
            self._engine = InferenceEngine(self.inference_model)
            
            # 设置进度回调
            self._engine.set_progress_callback(self._on_engine_progress)
            
            self.progress.emit(10)
            
            # 执行推理
            self.log.emit(f"⚙️  正在运行 {self.strategy} 推理...")
            
            result = None
            if self.strategy == 'large_image_block':
                # 大图分块推理
                if not self.output_path:
                    raise ValueError("大图分块推理需要指定输出路径")
                    
                self.log.emit(f"📁 输出路径: {self.output_path}")
                
                result = self._engine.large_image_block_inference(
                    self.image_path,
                    self.output_path,
                    crop_size=self.inference_params['crop_size'],
                    overlap_rate=self.inference_params['overlap_rate'],
                    enable_tta=self.inference_params['enable_tta']
                )
                
            elif self.strategy == 'sliding_window':
                # 滑窗推理
                result = self._engine.sliding_window_inference(
                    self.image_path,
                    crop_size=self.inference_params['crop_size'],
                    stride=self.inference_params['stride'],
                    batch_size=self.inference_params['batch_size'],
                    enable_tta=self.inference_params['enable_tta']
                )
                
            elif self.strategy == 'resize':
                # 全图缩放推理
                result = self._engine.resize_inference(
                    self.image_path,
                    enable_tta=self.inference_params['enable_tta']
                )
                
            else:
                raise ValueError(f"未知的推理策略: {self.strategy}")
                
            self.progress.emit(90)
            
            # 检查是否被取消
            if self._cancel_requested:
                self.log.emit("🛑 推理已取消")
                self.cancelled.emit()
                return
            
            if result is None:
                raise RuntimeError("推理返回结果为空")
                
            self.finished.emit(self.image_path, result, self.inference_params)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.log.emit(f"❌ 后台推理异常: {str(e)}")
            self.error.emit(f"{str(e)}\n\n{error_details}")


class InferencePanel(QWidget):
    """推理可视化面板"""
    
    # 信号定义
    model_loaded = Signal(dict)  # 模型加载完成信号
    inference_started = Signal()  # 推理开始信号
    inference_finished = Signal(dict)  # 推理完成信号
    inference_error = Signal(str)  # 推理错误信号
    log_message = Signal(str)  # 日志消息信号
    
    # 同步信号：当用户在推理面板选择输入路径时发出
    # 用于同步到左侧 GIS 图层控制
    input_path_selected = Signal(str)  # 参数: 选择的图像文件路径
    
    # 新增：预测初始化信号 (用于通知左侧图层列表显示占位符)
    # 参数: (input_path, output_filename_with_extension)
    prediction_initializing = Signal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.inference_model = None
        self.last_inference_result = None  # 保存最后一次推理结果
        
        # 同步控制标志 - 防止信号循环
        # 当从外部调用 set_image_path 时设为 True，阻止再次发出 input_path_selected 信号
        self._suppress_sync = False
        
        # 推理状态追踪
        self._is_inferencing = False
        self._inference_engine = None  # 保存引用以便取消
        
        self._setup_ui()
        self._connect_signals()
        self._init_inference_config()
    
    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)  # 压缩边距
        layout.setSpacing(4)  # 压缩组件间距
        
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
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距
        
        # === 新增：模型库选择区 ===
        self.label_modelRegistry = QLabel("已训练模型库:")
        registry_layout = QHBoxLayout()
        self.comboBox_modelRegistry = QComboBox()
        self.comboBox_modelRegistry.addItem("请选择历史训练模型...", userData=None)
        
        self.pushButton_refreshRegistry = QPushButton("🔄 刷新")
        self.pushButton_refreshRegistry.setMaximumWidth(60)
        
        registry_layout.addWidget(self.comboBox_modelRegistry)
        registry_layout.addWidget(self.pushButton_refreshRegistry)
        form_layout.addRow(self.label_modelRegistry, registry_layout)
        
        # 分隔线
        line_reg = QFrame()
        line_reg.setFrameShape(QFrame.HLine)
        line_reg.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line_reg)
        
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
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距
        
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
        
        # 输入影像选择（支持从 GIS 图层同步）
        self.label_inputPath = QLabel("输入影像:")
        input_layout = QHBoxLayout()
        self.lineEdit_inputPath = QLineEdit()
        self.lineEdit_inputPath.setPlaceholderText("选择图像文件或从 GIS 图层同步")
        self.lineEdit_inputPath.setReadOnly(True)  # 只读，防止手动输入
        self.pushButton_browseInput = QPushButton("浏览...")
        input_layout.addWidget(self.lineEdit_inputPath)
        input_layout.addWidget(self.pushButton_browseInput)
        form_layout.addRow(self.label_inputPath, input_layout)
        
        # 输出路径选择（自动保存预览PNG）
        self.label_outputPath = QLabel("输出路径 (预览PNG):")
        output_layout = QHBoxLayout()
        self.lineEdit_outputPath = QLineEdit()
        self.lineEdit_outputPath.setPlaceholderText("推理完成后自动保存预览PNG的路径（默认为输入图像所在目录）")
        self.lineEdit_outputPath.setReadOnly(True)  # 只读，防止手动输入
        self.lineEdit_outputPath.setToolTip("推理完成后会自动保存一个PNG格式的预览图到此路径")
        self.pushButton_browseOutputPath = QPushButton("浏览...")
        self.pushButton_browseOutputPath.setToolTip("选择自动保存预览PNG的文件夹")
        output_layout.addWidget(self.lineEdit_outputPath)
        output_layout.addWidget(self.pushButton_browseOutputPath)
        form_layout.addRow(self.label_outputPath, output_layout)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line1)
        
        # 推理策略模式选择（滑窗/全图缩放/大图分块）
        self.label_strategyMode = QLabel("策略模式:")
        strategy_layout = QHBoxLayout()
        self.radioButton_slidingWindow = QRadioButton("滑窗推理")
        self.radioButton_slidingWindow.setChecked(True)
        self.radioButton_resize = QRadioButton("全图缩放")
        self.radioButton_largeImageBlock = QRadioButton("大图分块 (GDAL)")
        strategy_layout.addWidget(self.radioButton_slidingWindow)
        strategy_layout.addWidget(self.radioButton_resize)
        strategy_layout.addWidget(self.radioButton_largeImageBlock)
        strategy_layout.addStretch()
        self.buttonGroup_strategyMode = QButtonGroup(self)
        self.buttonGroup_strategyMode.addButton(self.radioButton_slidingWindow)
        self.buttonGroup_strategyMode.addButton(self.radioButton_resize)
        self.buttonGroup_strategyMode.addButton(self.radioButton_largeImageBlock)
        form_layout.addRow(self.label_strategyMode, strategy_layout)
        
        # 策略说明
        self.label_strategyNote = QLabel(
            "• 滑窗推理: 适用于中等大小图像\n"
            "• 全图缩放: 仅用于小尺寸图像快速预览\n"
            "• 大图分块: 适用于超大遥感影像（需要GDAL）"
        )
        self.label_strategyNote.setWordWrap(True)
        self.label_strategyNote.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        form_layout.addRow("", self.label_strategyNote)
        
        # 滑窗参数 - 窗口大小
        self.label_cropSize = QLabel("窗口大小 (Crop Size):")
        self.spinBox_cropSize = QSpinBox()
        self.spinBox_cropSize.setMinimum(256)
        self.spinBox_cropSize.setMaximum(2048)
        self.spinBox_cropSize.setSingleStep(64)
        self.spinBox_cropSize.setValue(1024)
        form_layout.addRow(self.label_cropSize, self.spinBox_cropSize)
        
        # 滑窗参数 - 步长 / 大图分块参数 - 重叠率
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
        
        # 大图分块 - 重叠率
        self.label_overlapRate = QLabel("重叠率 (Overlap Rate):")
        overlap_layout = QHBoxLayout()
        self.doubleSpinBox_overlapRate = QDoubleSpinBox()
        self.doubleSpinBox_overlapRate.setMinimum(0.0)
        self.doubleSpinBox_overlapRate.setMaximum(0.5)
        self.doubleSpinBox_overlapRate.setSingleStep(0.05)
        self.doubleSpinBox_overlapRate.setValue(0.2)
        self.doubleSpinBox_overlapRate.setVisible(False)
        self.label_overlapHint = QLabel("大图分块模式的重叠率")
        self.label_overlapHint.setStyleSheet("color: #888; font-size: 10px;")
        self.label_overlapHint.setVisible(False)
        overlap_layout.addWidget(self.doubleSpinBox_overlapRate)
        overlap_layout.addWidget(self.label_overlapHint)
        overlap_layout.addStretch()
        form_layout.addRow(self.label_overlapRate, overlap_layout)
        
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
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距
        
        # 运行推理按钮
        self.pushButton_runInference = QPushButton("运行推理 (Run Inference)")
        form_layout.addRow(self.pushButton_runInference)
        
        # 批量推理按钮
        self.pushButton_batchInference = QPushButton("批量推理 (Batch Inference)")
        form_layout.addRow(self.pushButton_batchInference)
        
        # 进度条
        self.label_inferenceProgress = QLabel("进度:")
        progress_layout = QHBoxLayout()
        self.progressBar_inference = QProgressBar()
        self.progressBar_inference.setValue(0)
        
        # 取消按钮
        self.pushButton_cancelInference = QPushButton("❌ 取消")
        self.pushButton_cancelInference.setToolTip("取消当前正在进行的推理任务")
        self.pushButton_cancelInference.setEnabled(False)  # 初始禁用
        self.pushButton_cancelInference.setMaximumWidth(80)
        
        progress_layout.addWidget(self.progressBar_inference)
        progress_layout.addWidget(self.pushButton_cancelInference)
        form_layout.addRow(self.label_inferenceProgress, progress_layout)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)
        
        # 导出说明
        self.label_exportNote = QLabel(
            "💡 提示：推理完成后会自动保存预览PNG。\n"
            "   如需其他格式或正式存档，请使用下方的导出功能。"
        )
        self.label_exportNote.setWordWrap(True)
        self.label_exportNote.setStyleSheet("color: #0066cc; font-size: 10px; padding: 5px; background-color: #e6f2ff; border-radius: 3px;")
        form_layout.addRow("", self.label_exportNote)
        
        # 导出格式
        self.label_exportFormat = QLabel("导出格式:")
        export_format_layout = QHBoxLayout()
        self.checkBox_exportPNG = QCheckBox("PNG")
        self.checkBox_exportPNG.setChecked(True)
        self.checkBox_exportPNG.setToolTip("导出PNG格式的可视化结果")
        self.checkBox_exportNumpy = QCheckBox("NumPy (.npy)")
        self.checkBox_exportNumpy.setToolTip("导出NumPy数组格式，便于后续处理")
        self.checkBox_exportJSON = QCheckBox("JSON")
        self.checkBox_exportJSON.setToolTip("导出包含推理参数和统计信息的元数据")
        export_format_layout.addWidget(self.checkBox_exportPNG)
        export_format_layout.addWidget(self.checkBox_exportNumpy)
        export_format_layout.addWidget(self.checkBox_exportJSON)
        export_format_layout.addStretch()
        form_layout.addRow(self.label_exportFormat, export_format_layout)
        
        # 导出目录
        self.label_exportDir = QLabel("导出目录 (正式存档):")
        export_dir_layout = QHBoxLayout()
        self.lineEdit_exportDir = QLineEdit()
        self.lineEdit_exportDir.setPlaceholderText("选择正式导出目录（可选，默认使用输出路径）")
        self.lineEdit_exportDir.setToolTip("手动导出时使用的目录，用于正式存档")
        self.pushButton_browseExportDir = QPushButton("浏览...")
        self.pushButton_browseExportDir.setToolTip("选择导出目录")
        export_dir_layout.addWidget(self.lineEdit_exportDir)
        export_dir_layout.addWidget(self.pushButton_browseExportDir)
        form_layout.addRow(self.label_exportDir, export_dir_layout)
        
        # 导出结果按钮
        self.pushButton_exportResults = QPushButton("📤 导出结果（多格式）")
        self.pushButton_exportResults.setToolTip("将推理结果导出为选定的格式（PNG/NumPy/JSON）")
        form_layout.addRow(self.pushButton_exportResults)
        
        parent_layout.addWidget(self.groupBox_actionExport)
    
    def _create_inference_result_group(self, parent_layout):
        """创建推理结果显示区"""
        self.groupBox_inferenceResult = QGroupBox("推理结果 (Inference Result)")
        layout = QVBoxLayout(self.groupBox_inferenceResult)
        layout.setSpacing(3)  # 压缩行间距
        layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距
        
        self.label_inferenceResult = QLabel("暂无推理结果\n\n请加载模型并运行推理，结果将显示在此处。")
        self.label_inferenceResult.setWordWrap(True)
        self.label_inferenceResult.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label_inferenceResult.setMinimumHeight(100)
        layout.addWidget(self.label_inferenceResult)
        
        parent_layout.addWidget(self.groupBox_inferenceResult)

    def _connect_signals(self):
        """连接信号"""
        # 模型库区
        self.comboBox_modelRegistry.currentIndexChanged.connect(self._on_model_registry_changed)
        self.pushButton_refreshRegistry.clicked.connect(self._manual_refresh_registry)
        
        # 模型加载区
        self.pushButton_browseConfig.clicked.connect(self._browse_config_file)
        self.pushButton_browseCheckpoint.clicked.connect(self._browse_checkpoint_file)
        self.lineEdit_configFile.textChanged.connect(self._on_config_file_changed)
        self.pushButton_loadModel.clicked.connect(self._load_inference_model)
        
        # 推理模式切换
        self.radioButton_batchInference.toggled.connect(self._on_inference_mode_changed)
        
        # 策略模式切换
        self.radioButton_slidingWindow.toggled.connect(self._on_strategy_mode_changed)
        self.radioButton_resize.toggled.connect(self._on_strategy_mode_changed)
        self.radioButton_largeImageBlock.toggled.connect(self._on_strategy_mode_changed)
        
        # 输入影像浏览
        self.pushButton_browseInput.clicked.connect(self._browse_input_image)
        
        # 输出路径浏览
        self.pushButton_browseOutputPath.clicked.connect(self._browse_output_path)
        
        # 导出目录浏览
        self.pushButton_browseExportDir.clicked.connect(self._browse_export_dir)
        
        # 推理执行
        self.pushButton_runInference.clicked.connect(self._run_inference)
        self.pushButton_batchInference.clicked.connect(self._run_batch_inference)
        self.pushButton_cancelInference.clicked.connect(self._cancel_inference)
        
        # 导出结果
        self.pushButton_exportResults.clicked.connect(self._export_results)
        
    def scan_trained_models(self, data_root=None):
        """扫描已训练模型库"""
        if data_root:
            self._current_data_root = data_root
        elif not hasattr(self, '_current_data_root') or not self._current_data_root:
            return
            
        work_dirs_path = os.path.join(self._current_data_root, 'work_dirs')
        if not os.path.exists(work_dirs_path):
            return
            
        current_data = self.comboBox_modelRegistry.currentData()
        
        self.comboBox_modelRegistry.blockSignals(True)
        self.comboBox_modelRegistry.clear()
        self.comboBox_modelRegistry.addItem("请选择历史训练模型或者手动指定下方文件...", userData=None)
        
        try:
            dirs = [d for d in os.listdir(work_dirs_path) if os.path.isdir(os.path.join(work_dirs_path, d))]
            dirs.sort(key=lambda d: os.path.getmtime(os.path.join(work_dirs_path, d)), reverse=True)
            
            for d in dirs:
                dir_path = os.path.join(work_dirs_path, d)
                config_file = os.path.join(dir_path, 'train_config.py')
                
                if not os.path.exists(config_file):
                    continue
                    
                pth_files = [f for f in os.listdir(dir_path) if f.endswith('.pth')]
                if not pth_files:
                    continue
                    
                self.comboBox_modelRegistry.addItem(f"📦 {d}", userData=dir_path)
                
        except Exception as e:
            self._emit_log(f"⚠️  扫描模型库失败: {e}")
            
        self.comboBox_modelRegistry.blockSignals(False)
        
        if current_data:
            index = self.comboBox_modelRegistry.findData(current_data)
            if index >= 0:
                self.comboBox_modelRegistry.setCurrentIndex(index)
                
    def _manual_refresh_registry(self):
        """手动刷新模型库"""
        if hasattr(self, '_current_data_root') and self._current_data_root:
            self.scan_trained_models(self._current_data_root)
            self._emit_log("🔄 已刷新已训练模型库")
        else:
            self._emit_log("⚠️  无法刷新：尚未挂载数据集目录")
            
    def _on_model_registry_changed(self, index):
        """模型下拉框选择改变时触发"""
        if index <= 0:
            return
            
        dir_path = self.comboBox_modelRegistry.currentData()
        if not dir_path or not os.path.exists(dir_path):
            return
            
        config_file = os.path.join(dir_path, 'train_config.py')
        
        pth_files = [f for f in os.listdir(dir_path) if f.endswith('.pth')]
        best_pth = None
        
        for pth in pth_files:
            if 'best' in pth.lower():
                best_pth = pth
                break
                
        if not best_pth and pth_files:
            best_pth = max(pth_files, key=lambda f: os.path.getmtime(os.path.join(dir_path, f)))
            
        if os.path.exists(config_file):
            self.lineEdit_configFile.setText(config_file)
            
        if best_pth:
            self.lineEdit_checkpointFile.setText(os.path.join(dir_path, best_pth))
            
        self._emit_log(f"✅ 从库中自动填充了模型配置: {os.path.basename(dir_path)}")
        
    def select_model_by_dir(self, work_dir):
        """外部调用：强制下拉框选中指定的目录"""
        if not work_dir:
            return False
            
        normalized_dir = os.path.normpath(work_dir)
        for i in range(self.comboBox_modelRegistry.count()):
            item_data = self.comboBox_modelRegistry.itemData(i)
            if item_data and os.path.normpath(item_data) == normalized_dir:
                self.comboBox_modelRegistry.setCurrentIndex(i)
                return True
        return False
    
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
        # 批量模式时，输入影像框应该支持选择目录，但我们统一使用程序化控制
        # 因此此处不再禁用/启用控件
        pass
    
    def _on_strategy_mode_changed(self):
        """策略模式切换"""
        is_sliding_window = self.radioButton_slidingWindow.isChecked()
        is_large_image = self.radioButton_largeImageBlock.isChecked()
        
        # 滑窗模式：显示步长，隐藏重叠率
        self.spinBox_stride.setVisible(is_sliding_window)
        self.label_strideHint.setVisible(is_sliding_window)
        
        # 大图分块模式：显示重叠率，隐藏步长
        self.doubleSpinBox_overlapRate.setVisible(is_large_image)
        self.label_overlapHint.setVisible(is_large_image)
        
        # 更新标签文本
        if is_large_image:
            self.label_stride.setVisible(False)
            self.label_overlapRate.setVisible(True)
        else:
            self.label_stride.setVisible(is_sliding_window)
            self.label_overlapRate.setVisible(False)
        
        # 窗口大小和批大小对全图缩放模式不可用
        is_resize = self.radioButton_resize.isChecked()
        self.spinBox_cropSize.setEnabled(not is_resize)
        self.spinBox_batchSize.setEnabled(is_sliding_window)
    
    def _browse_input_image(self):
        """浏览选择输入影像"""
        if self.is_single_image_mode():
            # 单图模式：选择文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择要推理的图像",
                "",
                "Image Files (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;All Files (*.*)"
            )
            if file_path:
                self.lineEdit_inputPath.setText(file_path)
                # 发出同步信号
                if not self._suppress_sync:
                    self.input_path_selected.emit(file_path)
        else:
            # 批量模式：选择目录
            dir_path = QFileDialog.getExistingDirectory(
                self,
                "选择批量推理图像目录",
                "",
                QFileDialog.Option.ShowDirsOnly
            )
            if dir_path:
                self.lineEdit_inputPath.setText(dir_path)
    
    def _browse_output_path(self):
        """浏览选择输出路径（自动保存预览PNG）"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择自动保存预览PNG的文件夹",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.lineEdit_outputPath.setText(dir_path)
            self._emit_log(f"✅ [推理配置] 预览PNG输出路径已设置: {dir_path}")
    
    def _generate_output_filename(self, input_path: str) -> str:
        """
        生成输出文件名（自动命名规则）
        
        规则：input.jpg -> input_pred_v1
        注意：不含扩展名，扩展名由具体保存逻辑决定
        
        Args:
            input_path: 输入图像路径
            
        Returns:
            输出文件名（不含扩展名）
        """
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        # 用户需求：input.tif -> input_pred_v1.png
        output_filename = f"{base_name}_pred_v1"
        return output_filename
    
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
        
        # 2. 使用已选择的输入影像路径
        image_path = self.lineEdit_inputPath.text().strip()
        
        if not image_path:
            self._emit_log("⚠️  未选择图像文件")
            QMessageBox.warning(
                self, 
                "未选择图像", 
                "请先在'输入影像'中选择要推理的图像，\n或从 GIS 图层中同步图像。"
            )
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
                self._emit_log(f"⚠️  检测到超大尺寸图像，建议使用大图分块推理")
                
                # 如果当前选择的是全图缩放或滑窗推理，强烈建议切换
                if self.radioButton_resize.isChecked():
                    reply = QMessageBox.question(
                        self,
                        "超大图像警告",
                        f"检测到超大尺寸图像 ({img_width} x {img_height})。\n\n"
                        f"当前选择的是'全图缩放'模式，可能导致内存不足。\n"
                        f"建议切换到'大图分块 (GDAL)'模式。\n\n"
                        f"是否继续使用全图缩放模式？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.No:
                        self._emit_log("⚠️  用户取消推理")
                        return
                
                elif self.radioButton_slidingWindow.isChecked():
                    reply = QMessageBox.warning(
                        self,
                        "超大图像警告",
                        f"检测到超大尺寸图像 ({img_width} x {img_height} = {img_width*img_height/1000000:.1f}M像素)。\n\n"
                        f"⚠️ 重要提示：\n"
                        f"'滑窗推理'模式需要在内存中创建完整的结果掩码，\n"
                        f"对于如此大的图像会导致内存溢出！\n\n"
                        f"系统将跳过实际推理以保护内存。\n\n"
                        f"✅ 强烈建议：\n"
                        f"请切换到'大图分块 (GDAL)'模式进行真正的推理！\n\n"
                        f"是否继续（将不会进行实际推理）？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.No:
                        self._emit_log("⚠️  用户取消推理，建议切换到大图分块模式")
                        return
            
        except Exception as e:
            self._emit_log(f"❌ 图像读取失败: {e}")
            QMessageBox.critical(self, "图像读取失败", f"无法读取图像文件。\n\n错误信息:\n{str(e)}")
            return
        
        # 发送推理开始信号
        self.inference_started.emit()
        self._emit_log("🚀 开始单图推理...")
        
        # 发送同步信号到左侧 GIS 图层控制（如果未被抑制）
        if not self._suppress_sync:
            self.input_path_selected.emit(image_path)
        
        # 禁用推理按钮，防止重复点击
        self.pushButton_runInference.setEnabled(False)
        self.progressBar_inference.setValue(0)
        
        # 获取推理配置
        if self.radioButton_largeImageBlock.isChecked():
            strategy = 'large_image_block'
        elif self.radioButton_resize.isChecked():
            strategy = 'resize'
        else:
            strategy = 'sliding_window'
        
        inference_params = {
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'overlap_rate': self.doubleSpinBox_overlapRate.value(),
            'batch_size': self.spinBox_batchSize.value(),
            'enable_tta': self.checkBox_enableTTA.isChecked(),
            'conf_threshold': self.doubleSpinBox_confThreshold.value()
        }
        
        self._emit_log(f"   策略模式: {strategy}")
        if strategy == 'sliding_window':
            self._emit_log(f"   窗口大小: {inference_params['crop_size']}")
            self._emit_log(f"   步长: {inference_params['stride']}")
            self._emit_log(f"   批大小: {inference_params['batch_size']}")
        elif strategy == 'large_image_block':
            self._emit_log(f"   窗口大小: {inference_params['crop_size']}")
            self._emit_log(f"   重叠率: {inference_params['overlap_rate']}")
        self._emit_log(f"   TTA增强: {'启用' if inference_params['enable_tta'] else '禁用'}")
        
        # ========== 新增：通知图层列表添加占位符 ==========
        # 1. 确定输出文件名和扩展名
        base_output_name = self._generate_output_filename(image_path)
        if strategy == 'large_image_block':
            ext = ".tif"
        else:
            ext = ".png" # 默认保存为PNG
            
        expected_output_filename = f"{base_output_name}{ext}"
        
        # 2. 发送信号
        self.prediction_initializing.emit(image_path, expected_output_filename)
        self._emit_log(f"⏳ 预留图层位置: {expected_output_filename}")
        # ===============================================
        
        # 使用 QThread 异步执行推理
        self._start_worker(image_path, strategy, inference_params)

    def _start_worker(self, image_path: str, strategy: str, inference_params: dict):
        """启动后台工作线程"""
        # 准备大图模式需要的 output_path
        output_path = None
        if strategy == 'large_image_block':
            # 获取输出目录
            output_dir = self.lineEdit_outputPath.text().strip()
            if not output_dir:
                output_dir = os.path.dirname(image_path)
                self._emit_log(f"⚠️  未设置输出路径，使用默认路径: {output_dir}")
            
            # 生成文件名
            output_filename = self._generate_output_filename(image_path)
            output_path = os.path.join(output_dir, f"{output_filename}.tif") # 注意这里是大图模式特有的后缀
        
        # 创建并启动 Worker
        self._inference_worker = InferenceWorker(
            self.inference_model,
            image_path,
            strategy,
            inference_params,
            output_path
        )
        
        # 连接信号
        self._inference_worker.log.connect(self._emit_log)
        self._inference_worker.progress.connect(self.progressBar_inference.setValue)
        self._inference_worker.finished.connect(self._on_worker_finished)
        self._inference_worker.error.connect(self._on_worker_error)
        self._inference_worker.cancelled.connect(self._on_worker_cancelled)  # 取消信号
        self._inference_worker.finished.connect(self._cleanup_worker)
        self._inference_worker.error.connect(self._cleanup_worker)
        self._inference_worker.cancelled.connect(self._cleanup_worker)
        
        # 启用取消按钮
        self._is_inferencing = True
        self.pushButton_cancelInference.setEnabled(True)
        
        # 启动
        self._inference_worker.start()
        
    def _on_worker_finished(self, image_path: str, result: dict, inference_params: dict):
        """后台推理完成处理"""
        self.progressBar_inference.setValue(100)
        
        success = result.get('success', False)
        self._emit_log(f"📊 推理结果状态: {'成功' if success else '失败'}")
        
        if success:
            self._handle_inference_success(image_path, result, inference_params)
        else:
            error_msg = result.get('error', '未知错误')
            self._handle_inference_error(error_msg)
            
    def _on_worker_error(self, error_msg: str):
        """后台推理错误处理"""
        self._handle_inference_error(error_msg)
        
    def _cleanup_worker(self):
        """清理 Worker 资源"""
        self.pushButton_runInference.setEnabled(True)
        self.pushButton_cancelInference.setEnabled(False)  # 禁用取消按钮
        self._is_inferencing = False
        if hasattr(self, '_inference_worker'):
            self._inference_worker.deleteLater()
            self._inference_worker = None
    
    def _cancel_inference(self):
        """取消当前推理任务"""
        if not self._is_inferencing:
            self._emit_log("⚠️  当前没有正在进行的推理任务")
            return
        
        if hasattr(self, '_inference_worker') and self._inference_worker:
            self._emit_log("🛑 正在取消推理...")
            self._inference_worker.request_cancel()
            self.pushButton_cancelInference.setEnabled(False)
            self.pushButton_cancelInference.setText("取消中...")
        else:
            self._emit_log("⚠️  无法取消：Worker 不存在")
    
    def _on_worker_cancelled(self):
        """推理被取消时的处理"""
        self._emit_log("✅ 推理已成功取消")
        self.progressBar_inference.setValue(0)
        self.pushButton_cancelInference.setText("❌ 取消")
        self.label_inferenceResult.setText("推理已取消\\n\\n可以重新配置参数后再次运行推理。")
    
    def _handle_inference_success(self, image_path: str, result: dict, inference_params: dict):
        """处理推理成功的结果"""
        try:
            # 提取结果信息
            mask = result.get('mask')
            image_shape = result.get('image_shape', (0, 0))
            strategy = result.get('strategy', 'unknown')
            params = result.get('params', {})
            
            # 构建结果显示文本
            use_real_model = result.get('use_real_model', False)
            
            result_text = f"✅ 推理完成！\n\n"
            
            # 显示推理模式
            if use_real_model:
                result_text += f"🚀 使用真实模型推理（MMSegmentation）\n\n"
            else:
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
            
            # 大图分块推理的特殊处理
            if strategy == 'large_image_block':
                output_path = result.get('output_path', '')
                temp_dir = result.get('temp_dir', '')
                
                result_text += f"\n大图分块推理结果:\n"
                result_text += f"  • 输出文件: {os.path.basename(output_path)}\n"
                result_text += f"  • 分块临时目录: {os.path.basename(temp_dir)}\n"
                result_text += f"  • 分块数量: {params.get('x_num', 0)} x {params.get('y_num', 0)} = {params.get('total_blocks', 0)}\n"
                
                # 更新结果显示
                self.label_inferenceResult.setText(result_text)
                
                # 保存推理结果
                self.last_inference_result = {
                    'image_path': image_path,
                    'output_path': output_path,
                    'result': result,
                    'params': inference_params
                }
                
                # 发送推理完成信号
                self.inference_finished.emit(result)
                
                self._emit_log("✅ 大图分块推理完成")
                self._emit_log(f"   输出文件: {output_path}")
                
                # 提示用户
                QMessageBox.information(
                    self,
                    "推理完成",
                    f"大图分块推理已成功完成！\n\n"
                    f"图像: {os.path.basename(image_path)}\n"
                    f"输出: {output_path}\n"
                    f"分块数: {params.get('total_blocks', 0)}\n\n"
                    f"结果已保存为GeoTIFF格式。"
                )
                return
            
            # 统计类别分布（非大图分块模式）
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
            
            # 自动保存预览PNG（如果有掩码数据）
            saved_path = None
            if mask is not None:
                try:
                    # 获取输出路径
                    output_dir = self.lineEdit_outputPath.text().strip()
                    if not output_dir:
                        output_dir = os.path.dirname(image_path)
                        self._emit_log(f"⚠️  未设置输出路径，预览PNG将保存到默认路径: {output_dir}")
                    
                    # 生成输出文件名（自动命名规则：input.jpg -> input_pred_v1.png）
                    base_output_name = self._generate_output_filename(image_path)
                    output_filename = f"{base_output_name}.png"
                    saved_path = os.path.join(output_dir, output_filename)
                    
                    # 保存为PNG格式（预览用）
                    from PIL import Image
                    result_image = Image.fromarray(mask.astype(np.uint8))
                    result_image.save(saved_path)
                    
                    self._emit_log(f"✅ 预览PNG已自动保存: {saved_path}")
                    
                    # 更新last_inference_result，添加保存路径
                    self.last_inference_result['saved_path'] = saved_path
                    
                except Exception as save_error:
                    self._emit_log(f"⚠️  预览PNG自动保存失败: {save_error}")
            
            # 发送推理完成信号
            self.inference_finished.emit(result)
            
            self._emit_log("✅ 推理完成")
            if mask is not None:
                self._emit_log(f"   检测到 {len(unique_classes)} 个类别")
            else:
                self._emit_log(f"   超大图像模式：未生成完整掩码（正常）")
            
            # 提示用户可以导出结果
            message = f"推理已成功完成！\n\n图像: {os.path.basename(image_path)}\n策略: {strategy}\n"
            if saved_path:
                message += f"\n✅ 预览PNG已自动保存至:\n{saved_path}\n"
                message += "\n💡 提示：如需其他格式（NumPy/JSON）或正式存档，\n请使用下方的'导出结果'功能。"
            else:
                message += "\n您可以在下方查看详细结果，或点击'导出结果'保存推理结果。"
            
            QMessageBox.information(
                self,
                "推理完成",
                message
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
        
        batch_dir = self.lineEdit_inputPath.text().strip()
        if not batch_dir or not os.path.isdir(batch_dir):
            QMessageBox.warning(self, "输入目录无效", "请选择有效的批量推理图像目录。")
            return
        
        self.inference_started.emit()
        self._emit_log(f"🚀 开始批量推理: {batch_dir}")
        
        # TODO: 实现实际的批量推理逻辑
        self.label_inferenceResult.setText("批量推理功能待实现...\n\n请在实际项目中集成 MMSegmentation 推理 API。")
    
    def _export_results(self):
        """导出推理结果"""
        # 1. 检查是否有推理结果
        if not self.last_inference_result:
            self._emit_log("⚠️  没有可导出的推理结果")
            QMessageBox.warning(
                self, 
                "无推理结果", 
                "请先运行推理，然后再导出结果。"
            )
            return
        
        # 2. 检查导出目录
        export_dir = self.lineEdit_exportDir.text().strip()
        if not export_dir:
            # 如果没有设置导出目录，使用输出路径
            export_dir = self.lineEdit_outputPath.text().strip()
            if not export_dir:
                # 如果输出路径也没有，使用输入图像所在目录
                input_path = self.last_inference_result.get('image_path', '')
                if input_path:
                    export_dir = os.path.dirname(input_path)
                else:
                    QMessageBox.warning(
                        self, 
                        "导出目录未设置", 
                        "请先选择导出目录。"
                    )
                    return
            
            self.lineEdit_exportDir.setText(export_dir)
        
        # 确保导出目录存在
        if not os.path.exists(export_dir):
            try:
                os.makedirs(export_dir)
                self._emit_log(f"📁 创建导出目录: {export_dir}")
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "创建目录失败", 
                    f"无法创建导出目录。\n\n错误信息:\n{e}"
                )
                return
        
        # 3. 获取导出格式
        export_png = self.checkBox_exportPNG.isChecked()
        export_numpy = self.checkBox_exportNumpy.isChecked()
        export_json = self.checkBox_exportJSON.isChecked()
        
        if not (export_png or export_numpy or export_json):
            QMessageBox.warning(
                self, 
                "未选择导出格式", 
                "请至少选择一种导出格式（PNG、NumPy 或 JSON）。"
            )
            return
        
        # 4. 执行导出
        self._emit_log(f"📤 开始导出结果到: {export_dir}")
        
        try:
            image_path = self.last_inference_result.get('image_path', '')
            base_name = os.path.splitext(os.path.basename(image_path))[0] if image_path else 'result'
            mask = self.last_inference_result.get('mask')
            
            exported_files = []
            
            # 导出 PNG 格式
            if export_png and mask is not None:
                png_path = os.path.join(export_dir, f"{base_name}_Result.png")
                from PIL import Image
                result_image = Image.fromarray(mask.astype(np.uint8))
                result_image.save(png_path)
                exported_files.append(png_path)
                self._emit_log(f"✅ PNG 已导出: {os.path.basename(png_path)}")
            
            # 导出 NumPy 格式
            if export_numpy and mask is not None:
                npy_path = os.path.join(export_dir, f"{base_name}_Result.npy")
                np.save(npy_path, mask)
                exported_files.append(npy_path)
                self._emit_log(f"✅ NumPy 已导出: {os.path.basename(npy_path)}")
            
            # 导出 JSON 格式（包含元数据）
            if export_json:
                import json
                json_path = os.path.join(export_dir, f"{base_name}_Result.json")
                
                # 构建元数据
                metadata = {
                    'image_path': image_path,
                    'image_shape': self.last_inference_result.get('image_shape', []),
                    'strategy': self.last_inference_result.get('strategy', 'unknown'),
                    'params': self.last_inference_result.get('params', {}),
                    'unique_classes': self.last_inference_result.get('unique_classes', []),
                    'class_counts': self.last_inference_result.get('class_counts', {}),
                    'model_name': self.inference_model.get('model_name', 'Unknown') if self.inference_model else 'Unknown',
                    'export_time': __import__('datetime').datetime.now().isoformat()
                }
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                exported_files.append(json_path)
                self._emit_log(f"✅ JSON 已导出: {os.path.basename(json_path)}")
            
            # 5. 显示导出成功消息
            if exported_files:
                files_list = '\n'.join([f"  • {os.path.basename(f)}" for f in exported_files])
                QMessageBox.information(
                    self,
                    "导出成功",
                    f"推理结果已成功导出！\n\n导出目录:\n{export_dir}\n\n导出文件:\n{files_list}"
                )
                self._emit_log(f"✅ 导出完成，共 {len(exported_files)} 个文件")
            else:
                QMessageBox.warning(
                    self,
                    "导出失败",
                    "没有可导出的数据。\n\n注意：大图分块模式不生成完整掩码，无法导出 PNG/NumPy 格式。"
                )
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self._emit_log(f"❌ 导出失败: {e}")
            self._emit_log(f"详细错误:\n{error_details}")
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出过程中发生错误。\n\n错误信息:\n{e}"
            )
    
    def get_inference_config(self) -> dict:
        """获取当前推理配置"""
        return {
            'config_file': self.lineEdit_configFile.text(),
            'checkpoint_file': self.lineEdit_checkpointFile.text(),
            'device': self.comboBox_device.currentText(),
            'inference_mode': 'batch' if self.radioButton_batchInference.isChecked() else 'single',
            'input_path': self.lineEdit_inputPath.text(),
            'strategy_mode': (
                'large_image_block' if self.radioButton_largeImageBlock.isChecked() 
                else 'resize' if self.radioButton_resize.isChecked() 
                else 'sliding_window'
            ),
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'overlap_rate': self.doubleSpinBox_overlapRate.value(),
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
    
    # ==================== 双向同步方法 ====================
    
    def is_single_image_mode(self) -> bool:
        """
        检查当前是否为单图推理模式
        
        Returns:
            bool: True 表示单图推理模式，False 表示批量推理模式
        """
        return self.radioButton_singleImage.isChecked()
    
    def set_image_path(self, path: str) -> None:
        """
        设置推理输入图像路径（由外部调用，用于接收同步）
        
        用于从左侧 GIS 图层控制同步过来的路径。
        会抑制信号发送，防止循环同步。
        
        Args:
            path: 图像文件路径
        """
        if not path or not os.path.exists(path):
            self._emit_log(f"⚠️ 同步路径无效或不存在: {path}")
            return
        
        # 设置标志位，防止信号循环
        self._suppress_sync = True
        
        try:
            # 直接设置到输入影像框
            self.lineEdit_inputPath.setText(path)
            self._emit_log(f"📥 已从 GIS 图层同步输入路径: {os.path.basename(path)}")
        finally:
            self._suppress_sync = False
    
    def set_batch_dir(self, dir_path: str) -> None:
        """
        设置批量推理目录（由外部调用，用于接收同步）
        
        Args:
            dir_path: 目录路径
        """
        if not dir_path or not os.path.isdir(dir_path):
            return
        
        self._suppress_sync = True
        try:
            self.lineEdit_inputPath.setText(dir_path)
        finally:
            self._suppress_sync = False
    
    def get_current_input_path(self) -> str:
        """
        获取当前的输入路径
        
        Returns:
            str: 当前配置的输入路径（输入影像框中的路径）
        """
        return self.lineEdit_inputPath.text().strip()

