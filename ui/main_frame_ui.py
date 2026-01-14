# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_frame.ui'
##
## Created by: Qt User Interface Compiler version 6.10.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QGraphicsView,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMenu, QMenuBar, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSpacerItem, QSplitter, QStatusBar, QStackedWidget, QTabWidget,
    QTextEdit, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QListView)
from ui.widgets.collapsible_widget import CollapsibleContainer, CollapsiblePanel
from ui.widgets.dataset_overview_widget import DatasetOverviewWidget
from ui.analysis_panel import AnalysisPanel
from ui.widgets.class_distribution_widget import ClassDistributionWidget
from ui.widgets.coverage_analysis_widget import CoverageAnalysisCard
from ui.widgets.health_check_widget import HealthCheckCard
from ui.inference_panel import InferencePanel

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1400, 900)
        self.action_open = QAction(MainWindow)
        self.action_open.setObjectName(u"action_open")
        self.action_save = QAction(MainWindow)
        self.action_save.setObjectName(u"action_save")
        self.action_exit = QAction(MainWindow)
        self.action_exit.setObjectName(u"action_exit")
        self.action_preferences = QAction(MainWindow)
        self.action_preferences.setObjectName(u"action_preferences")
        self.action_zoomIn = QAction(MainWindow)
        self.action_zoomIn.setObjectName(u"action_zoomIn")
        self.action_zoomOut = QAction(MainWindow)
        self.action_zoomOut.setObjectName(u"action_zoomOut")
        self.action_fitToWindow = QAction(MainWindow)
        self.action_fitToWindow.setObjectName(u"action_fitToWindow")
        self.action_train = QAction(MainWindow)
        self.action_train.setObjectName(u"action_train")
        self.action_inference = QAction(MainWindow)
        self.action_inference.setObjectName(u"action_inference")
        self.action_about = QAction(MainWindow)
        self.action_about.setObjectName(u"action_about")
        self.action_gridView = QAction(MainWindow)
        self.action_gridView.setObjectName(u"action_gridView")
        self.action_gridView.setCheckable(True)
        self.action_detailView = QAction(MainWindow)
        self.action_detailView.setObjectName(u"action_detailView")
        self.action_detailView.setCheckable(True)
        self.action_detailView.setChecked(True)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_main = QVBoxLayout(self.centralwidget)
        self.verticalLayout_main.setObjectName(u"verticalLayout_main")
        self.splitter_vertical = QSplitter(self.centralwidget)
        self.splitter_vertical.setObjectName(u"splitter_vertical")
        self.splitter_vertical.setOrientation(Qt.Orientation.Vertical)
        self.splitter_horizontal = QSplitter(self.splitter_vertical)
        self.splitter_horizontal.setObjectName(u"splitter_horizontal")
        self.splitter_horizontal.setOrientation(Qt.Orientation.Horizontal)
        self.leftPanel = QWidget(self.splitter_horizontal)
        self.leftPanel.setObjectName(u"leftPanel")
        self.verticalLayout_left = QVBoxLayout(self.leftPanel)
        self.verticalLayout_left.setObjectName(u"verticalLayout_left")
        self.verticalLayout_left.setContentsMargins(0, 0, 0, 0)
        self.groupBox_dataSource = QGroupBox(self.leftPanel)
        self.groupBox_dataSource.setObjectName(u"groupBox_dataSource")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(3)
        sizePolicy.setHeightForWidth(self.groupBox_dataSource.sizePolicy().hasHeightForWidth())
        self.groupBox_dataSource.setSizePolicy(sizePolicy)
        self.verticalLayout_dataSource = QVBoxLayout(self.groupBox_dataSource)
        self.verticalLayout_dataSource.setObjectName(u"verticalLayout_dataSource")
        self.treeWidget_dataSources = QTreeWidget(self.groupBox_dataSource)
        __qtreewidgetitem = QTreeWidgetItem()
        __qtreewidgetitem.setText(0, u"1");
        self.treeWidget_dataSources.setHeaderItem(__qtreewidgetitem)
        self.treeWidget_dataSources.setObjectName(u"treeWidget_dataSources")
        self.treeWidget_dataSources.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.treeWidget_dataSources.setHeaderHidden(True)

        self.verticalLayout_dataSource.addWidget(self.treeWidget_dataSources)

        self.pushButton_addSample = QPushButton(self.groupBox_dataSource)
        self.pushButton_addSample.setObjectName(u"pushButton_addSample")

        self.verticalLayout_dataSource.addWidget(self.pushButton_addSample)


        self.verticalLayout_left.addWidget(self.groupBox_dataSource)

        self.groupBox_layerControl = QGroupBox(self.leftPanel)
        self.groupBox_layerControl.setObjectName(u"groupBox_layerControl")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(1)
        sizePolicy1.setHeightForWidth(self.groupBox_layerControl.sizePolicy().hasHeightForWidth())
        self.groupBox_layerControl.setSizePolicy(sizePolicy1)
        self.verticalLayout_layerControl = QVBoxLayout(self.groupBox_layerControl)
        self.verticalLayout_layerControl.setObjectName(u"verticalLayout_layerControl")
        self.checkBox_overlayPrediction = QCheckBox(self.groupBox_layerControl)
        self.checkBox_overlayPrediction.setObjectName(u"checkBox_overlayPrediction")
        self.checkBox_overlayPrediction.setChecked(True)

        self.verticalLayout_layerControl.addWidget(self.checkBox_overlayPrediction)

        self.checkBox_baseImage = QCheckBox(self.groupBox_layerControl)
        self.checkBox_baseImage.setObjectName(u"checkBox_baseImage")
        self.checkBox_baseImage.setChecked(True)

        self.verticalLayout_layerControl.addWidget(self.checkBox_baseImage)

        self.checkBox_labelOnly = QCheckBox(self.groupBox_layerControl)
        self.checkBox_labelOnly.setObjectName(u"checkBox_labelOnly")
        self.checkBox_labelOnly.setChecked(False)

        self.verticalLayout_layerControl.addWidget(self.checkBox_labelOnly)

        self.horizontalLayout_opacity = QHBoxLayout()
        self.horizontalLayout_opacity.setObjectName(u"horizontalLayout_opacity")
        self.label_opacity = QLabel(self.groupBox_layerControl)
        self.label_opacity.setObjectName(u"label_opacity")

        self.horizontalLayout_opacity.addWidget(self.label_opacity)

        self.slider_opacity = QSlider(self.groupBox_layerControl)
        self.slider_opacity.setObjectName(u"slider_opacity")
        self.slider_opacity.setMinimum(0)
        self.slider_opacity.setMaximum(100)
        self.slider_opacity.setValue(70)
        self.slider_opacity.setOrientation(Qt.Orientation.Horizontal)

        self.horizontalLayout_opacity.addWidget(self.slider_opacity)

        self.label_opacityValue = QLabel(self.groupBox_layerControl)
        self.label_opacityValue.setObjectName(u"label_opacityValue")

        self.horizontalLayout_opacity.addWidget(self.label_opacityValue)


        self.verticalLayout_layerControl.addLayout(self.horizontalLayout_opacity)

        self.checkBox_swipeCompare = QCheckBox(self.groupBox_layerControl)
        self.checkBox_swipeCompare.setObjectName(u"checkBox_swipeCompare")
        self.checkBox_swipeCompare.setChecked(False)

        self.verticalLayout_layerControl.addWidget(self.checkBox_swipeCompare)

        self.horizontalLayout_swipe = QHBoxLayout()
        self.horizontalLayout_swipe.setObjectName(u"horizontalLayout_swipe")
        self.label_swipe = QLabel(self.groupBox_layerControl)
        self.label_swipe.setObjectName(u"label_swipe")

        self.horizontalLayout_swipe.addWidget(self.label_swipe)

        self.slider_swipe = QSlider(self.groupBox_layerControl)
        self.slider_swipe.setObjectName(u"slider_swipe")
        self.slider_swipe.setMinimum(0)
        self.slider_swipe.setMaximum(100)
        self.slider_swipe.setValue(50)
        self.slider_swipe.setOrientation(Qt.Orientation.Horizontal)
        self.slider_swipe.setEnabled(False)

        self.horizontalLayout_swipe.addWidget(self.slider_swipe)

        self.label_swipeValue = QLabel(self.groupBox_layerControl)
        self.label_swipeValue.setObjectName(u"label_swipeValue")

        self.horizontalLayout_swipe.addWidget(self.label_swipeValue)


        self.verticalLayout_layerControl.addLayout(self.horizontalLayout_swipe)


        self.verticalLayout_left.addWidget(self.groupBox_layerControl)

        self.splitter_horizontal.addWidget(self.leftPanel)
        self.centerPanel = QWidget(self.splitter_horizontal)
        self.centerPanel.setObjectName(u"centerPanel")
        self.verticalLayout_center = QVBoxLayout(self.centerPanel)
        self.verticalLayout_center.setObjectName(u"verticalLayout_center")
        self.verticalLayout_center.setContentsMargins(0, 0, 0, 0)
        
        # 使用 QStackedWidget 切换视图
        self.stackedWidget_views = QStackedWidget(self.centerPanel)
        self.stackedWidget_views.setObjectName(u"stackedWidget_views")
        
        # 页面0: 详情视图 (Detail View)
        self.page_detailView = QWidget()
        self.page_detailView.setObjectName(u"page_detailView")
        self.verticalLayout_detailView = QVBoxLayout(self.page_detailView)
        self.verticalLayout_detailView.setObjectName(u"verticalLayout_detailView")
        self.verticalLayout_detailView.setContentsMargins(0, 0, 0, 0)
        self.graphicsView_canvas = QGraphicsView(self.page_detailView)
        self.graphicsView_canvas.setObjectName(u"graphicsView_canvas")
        self.graphicsView_canvas.setMinimumSize(QSize(600, 400))
        self.verticalLayout_detailView.addWidget(self.graphicsView_canvas)
        self.stackedWidget_views.addWidget(self.page_detailView)
        
        # 页面1: 网格视图 (Grid View)
        self.page_gridView = QWidget()
        self.page_gridView.setObjectName(u"page_gridView")
        self.verticalLayout_gridView = QVBoxLayout(self.page_gridView)
        self.verticalLayout_gridView.setObjectName(u"verticalLayout_gridView")
        self.verticalLayout_gridView.setContentsMargins(0, 0, 0, 0)
        self.listWidget_thumbnails = QListWidget(self.page_gridView)
        self.listWidget_thumbnails.setObjectName(u"listWidget_thumbnails")
        self.listWidget_thumbnails.setViewMode(QListView.ViewMode.IconMode)
        self.listWidget_thumbnails.setIconSize(QSize(120, 120))
        self.listWidget_thumbnails.setGridSize(QSize(140, 160))  # 固定网格大小，留出文字空间
        self.listWidget_thumbnails.setSpacing(8)
        self.listWidget_thumbnails.setResizeMode(QListView.ResizeMode.Adjust)
        self.listWidget_thumbnails.setWordWrap(True)  # 文件名换行
        self.listWidget_thumbnails.setMovement(QListView.Movement.Static)
        self.listWidget_thumbnails.setMinimumSize(QSize(600, 400))
        self.verticalLayout_gridView.addWidget(self.listWidget_thumbnails)
        self.stackedWidget_views.addWidget(self.page_gridView)

        self.verticalLayout_center.addWidget(self.stackedWidget_views)

        self.splitter_horizontal.addWidget(self.centerPanel)
        self.rightPanel = QWidget(self.splitter_horizontal)
        self.rightPanel.setObjectName(u"rightPanel")
        self.verticalLayout_right = QVBoxLayout(self.rightPanel)
        self.verticalLayout_right.setObjectName(u"verticalLayout_right")
        self.verticalLayout_right.setContentsMargins(0, 0, 0, 0)
        
        # 右侧面板：上下文属性与控制 (Context & Control)
        self.tabWidget_contextControl = QTabWidget(self.rightPanel)
        self.tabWidget_contextControl.setObjectName(u"tabWidget_contextControl")
        
        # ========== Tab 1: 数据洞察 (Data Profile) ==========
        self.tab_dataProfile = QWidget()
        self.tab_dataProfile.setObjectName(u"tab_dataProfile")
        self.verticalLayout_dataProfile = QVBoxLayout(self.tab_dataProfile)
        self.verticalLayout_dataProfile.setObjectName(u"verticalLayout_dataProfile")
        self.verticalLayout_dataProfile.setContentsMargins(0, 0, 0, 0)
        
        # 使用 AnalysisPanel 智能分析面板
        self.analysis_panel = AnalysisPanel(self.tab_dataProfile)
        self.analysis_panel.setObjectName(u"analysis_panel")
        
        # === 顶部：数据集概览（永远可见）===
        self.panel_datasetOverview = CollapsiblePanel("数据集概览 (Dataset Overview)", expanded=True)
        self.widget_datasetOverview = DatasetOverviewWidget()
        self.widget_datasetOverview.setObjectName(u"widget_datasetOverview")
        self.panel_datasetOverview.add_widget(self.widget_datasetOverview)
        # 添加 Resplit 按钮到 Header（蓝色强调）
        self.btn_resplit = self.panel_datasetOverview.add_header_action(
            text="Resplit",
            icon_name='fa5s.sync-alt',
            icon_color='#2196F3',
            tooltip="重新划分数据集 (Train/Val/Test)"
        )
        self.btn_resplit.setEnabled(False)  # 默认禁用，有数据时启用
        self.analysis_panel.set_overview_widget(self.panel_datasetOverview)
        
        # === 底部：深度图表（可折叠面板容器）===
        self.collapsible_dataProfile = CollapsibleContainer()
        self.collapsible_dataProfile.setObjectName(u"collapsible_dataProfile")
        
        # 面板1: 类别分布 (Class Distribution)
        self.panel_classDistribution = self.collapsible_dataProfile.add_panel("类别分布", expanded=True)
        self.widget_classDistribution = ClassDistributionWidget()
        self.widget_classDistribution.setObjectName(u"widget_classDistribution")
        self.panel_classDistribution.add_widget(self.widget_classDistribution)
        # 将权重按钮添加到标题栏
        self.panel_classDistribution.add_header_widget(self.widget_classDistribution.get_header_button())
        
        # 面板2: 覆盖率分析 (Coverage Analysis)
        self.panel_coverageAnalysis = self.collapsible_dataProfile.add_panel("覆盖率分析", expanded=False)
        self.widget_coverageAnalysis = CoverageAnalysisCard()
        self.widget_coverageAnalysis.setObjectName(u"widget_coverageAnalysis")
        self.panel_coverageAnalysis.add_widget(self.widget_coverageAnalysis)
        
        # 面板3: 健康检查 (Health Check)
        self.panel_healthCheck = self.collapsible_dataProfile.add_panel("健康检查 (Health Check)", expanded=False)
        self.widget_healthCheck = HealthCheckCard()
        self.widget_healthCheck.setObjectName(u"widget_healthCheck")
        self.panel_healthCheck.add_widget(self.widget_healthCheck)
        # 将摘要控件添加到标题栏
        self.panel_healthCheck.add_header_widget(self.widget_healthCheck.get_header_widget())
        
        # 将深度图表设置为 AnalysisPanel 的底部组件
        self.analysis_panel.set_charts_widget(self.collapsible_dataProfile)
        
        self.verticalLayout_dataProfile.addWidget(self.analysis_panel)
        
        self.tabWidget_contextControl.addTab(self.tab_dataProfile, "")
        
        # ========== Tab 2: 任务配置 (Task Config) ==========
        self.tab_taskConfig = QWidget()
        self.tab_taskConfig.setObjectName(u"tab_taskConfig")
        self.verticalLayout_taskConfig = QVBoxLayout(self.tab_taskConfig)
        self.verticalLayout_taskConfig.setObjectName(u"verticalLayout_taskConfig")
        
        # 任务类型选择
        self.groupBox_taskType = QGroupBox(self.tab_taskConfig)
        self.groupBox_taskType.setObjectName(u"groupBox_taskType")
        self.verticalLayout_taskType = QVBoxLayout(self.groupBox_taskType)
        self.verticalLayout_taskType.setObjectName(u"verticalLayout_taskType")
        self.tabWidget_tasks = QTabWidget(self.groupBox_taskType)
        self.tabWidget_tasks.setObjectName(u"tabWidget_tasks")
        self.tab_train = QWidget()
        self.tab_train.setObjectName(u"tab_train")
        self.verticalLayout_train = QVBoxLayout(self.tab_train)
        self.verticalLayout_train.setObjectName(u"verticalLayout_train")
        self.label_trainInfo = QLabel(self.tab_train)
        self.label_trainInfo.setObjectName(u"label_trainInfo")
        self.verticalLayout_train.addWidget(self.label_trainInfo)
        self.tabWidget_tasks.addTab(self.tab_train, "")
        self.tab_inference = QWidget()
        self.tab_inference.setObjectName(u"tab_inference")
        self.verticalLayout_inference = QVBoxLayout(self.tab_inference)
        self.verticalLayout_inference.setObjectName(u"verticalLayout_inference")
        self.label_inferenceInfo = QLabel(self.tab_inference)
        self.label_inferenceInfo.setObjectName(u"label_inferenceInfo")
        self.verticalLayout_inference.addWidget(self.label_inferenceInfo)
        self.tabWidget_tasks.addTab(self.tab_inference, "")
        self.verticalLayout_taskType.addWidget(self.tabWidget_tasks)
        self.verticalLayout_taskConfig.addWidget(self.groupBox_taskType)
        
        # 参数配置
        self.groupBox_paramConfig = QGroupBox(self.tab_taskConfig)
        self.groupBox_paramConfig.setObjectName(u"groupBox_paramConfig")
        self.verticalLayout_paramConfig = QVBoxLayout(self.groupBox_paramConfig)
        self.verticalLayout_paramConfig.setObjectName(u"verticalLayout_paramConfig")
        self.scrollArea_params = QScrollArea(self.groupBox_paramConfig)
        self.scrollArea_params.setObjectName(u"scrollArea_params")
        self.scrollArea_params.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 256, 96))
        self.verticalLayout_scrollParams = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout_scrollParams.setObjectName(u"verticalLayout_scrollParams")
        self.label_paramPlaceholder = QLabel(self.scrollAreaWidgetContents)
        self.label_paramPlaceholder.setObjectName(u"label_paramPlaceholder")
        self.label_paramPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verticalLayout_scrollParams.addWidget(self.label_paramPlaceholder)
        self.verticalSpacer_params = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.verticalLayout_scrollParams.addItem(self.verticalSpacer_params)
        self.scrollArea_params.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout_paramConfig.addWidget(self.scrollArea_params)
        self.verticalLayout_taskConfig.addWidget(self.groupBox_paramConfig)
        
        # 操作按钮
        self.groupBox_actions = QGroupBox(self.tab_taskConfig)
        self.groupBox_actions.setObjectName(u"groupBox_actions")
        self.verticalLayout_actions = QVBoxLayout(self.groupBox_actions)
        self.verticalLayout_actions.setObjectName(u"verticalLayout_actions")
        self.pushButton_run = QPushButton(self.groupBox_actions)
        self.pushButton_run.setObjectName(u"pushButton_run")
        self.verticalLayout_actions.addWidget(self.pushButton_run)
        self.pushButton_stop = QPushButton(self.groupBox_actions)
        self.pushButton_stop.setObjectName(u"pushButton_stop")
        self.verticalLayout_actions.addWidget(self.pushButton_stop)
        self.pushButton_export = QPushButton(self.groupBox_actions)
        self.pushButton_export.setObjectName(u"pushButton_export")
        self.verticalLayout_actions.addWidget(self.pushButton_export)
        self.verticalLayout_taskConfig.addWidget(self.groupBox_actions)
        
        self.verticalSpacer_taskConfig = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.verticalLayout_taskConfig.addItem(self.verticalSpacer_taskConfig)
        
        self.tabWidget_contextControl.addTab(self.tab_taskConfig, "")
        
        # ========== Tab 3: 推理可视化 (Inference) ==========
        self.tab_inferenceVis = QWidget()
        self.tab_inferenceVis.setObjectName(u"tab_inferenceVis")
        self.verticalLayout_inferenceVis = QVBoxLayout(self.tab_inferenceVis)
        self.verticalLayout_inferenceVis.setObjectName(u"verticalLayout_inferenceVis")
        self.verticalLayout_inferenceVis.setContentsMargins(0, 0, 0, 0)
        
        # 使用新的 InferencePanel 组件
        self.inference_panel = InferencePanel(self.tab_inferenceVis)
        self.inference_panel.setObjectName(u"inference_panel")
        self.verticalLayout_inferenceVis.addWidget(self.inference_panel)
        
        self.tabWidget_contextControl.addTab(self.tab_inferenceVis, "")
        
        self.verticalLayout_right.addWidget(self.tabWidget_contextControl)

        self.splitter_horizontal.addWidget(self.rightPanel)
        self.splitter_vertical.addWidget(self.splitter_horizontal)
        self.bottomPanel = QWidget(self.splitter_vertical)
        self.bottomPanel.setObjectName(u"bottomPanel")
        self.verticalLayout_bottom = QVBoxLayout(self.bottomPanel)
        self.verticalLayout_bottom.setObjectName(u"verticalLayout_bottom")
        self.verticalLayout_bottom.setContentsMargins(0, 0, 0, 0)
        self.tabWidget_bottom = QTabWidget(self.bottomPanel)
        self.tabWidget_bottom.setObjectName(u"tabWidget_bottom")
        self.tab_logs = QWidget()
        self.tab_logs.setObjectName(u"tab_logs")
        self.verticalLayout_logs = QVBoxLayout(self.tab_logs)
        self.verticalLayout_logs.setObjectName(u"verticalLayout_logs")
        self.textEdit_logs = QTextEdit(self.tab_logs)
        self.textEdit_logs.setObjectName(u"textEdit_logs")
        self.textEdit_logs.setReadOnly(True)

        self.verticalLayout_logs.addWidget(self.textEdit_logs)

        self.tabWidget_bottom.addTab(self.tab_logs, "")
        self.tab_metrics = QWidget()
        self.tab_metrics.setObjectName(u"tab_metrics")
        self.verticalLayout_metrics = QVBoxLayout(self.tab_metrics)
        self.verticalLayout_metrics.setObjectName(u"verticalLayout_metrics")
        self.label_metricsPlaceholder = QLabel(self.tab_metrics)
        self.label_metricsPlaceholder.setObjectName(u"label_metricsPlaceholder")
        self.label_metricsPlaceholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout_metrics.addWidget(self.label_metricsPlaceholder)

        self.tabWidget_bottom.addTab(self.tab_metrics, "")
        self.tab_progress = QWidget()
        self.tab_progress.setObjectName(u"tab_progress")
        self.verticalLayout_progress = QVBoxLayout(self.tab_progress)
        self.verticalLayout_progress.setObjectName(u"verticalLayout_progress")
        self.label_progressInfo = QLabel(self.tab_progress)
        self.label_progressInfo.setObjectName(u"label_progressInfo")

        self.verticalLayout_progress.addWidget(self.label_progressInfo)

        self.progressBar_task = QProgressBar(self.tab_progress)
        self.progressBar_task.setObjectName(u"progressBar_task")
        self.progressBar_task.setValue(0)

        self.verticalLayout_progress.addWidget(self.progressBar_task)

        self.verticalSpacer_progress = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout_progress.addItem(self.verticalSpacer_progress)

        self.tabWidget_bottom.addTab(self.tab_progress, "")

        self.verticalLayout_bottom.addWidget(self.tabWidget_bottom)

        self.splitter_vertical.addWidget(self.bottomPanel)

        self.verticalLayout_main.addWidget(self.splitter_vertical)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1400, 33))
        self.menu_file = QMenu(self.menubar)
        self.menu_file.setObjectName(u"menu_file")
        self.menu_edit = QMenu(self.menubar)
        self.menu_edit.setObjectName(u"menu_edit")
        self.menu_view = QMenu(self.menubar)
        self.menu_view.setObjectName(u"menu_view")
        self.menu_tools = QMenu(self.menubar)
        self.menu_tools.setObjectName(u"menu_tools")
        self.menu_help = QMenu(self.menubar)
        self.menu_help.setObjectName(u"menu_help")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        self.statusbar.setSizeGripEnabled(True)
        MainWindow.setStatusBar(self.statusbar)
        self.toolBar = QToolBar(MainWindow)
        self.toolBar.setObjectName(u"toolBar")
        MainWindow.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolBar)

        self.menubar.addAction(self.menu_file.menuAction())
        self.menubar.addAction(self.menu_edit.menuAction())
        self.menubar.addAction(self.menu_view.menuAction())
        self.menubar.addAction(self.menu_tools.menuAction())
        self.menubar.addAction(self.menu_help.menuAction())
        self.menu_file.addAction(self.action_open)
        self.menu_file.addAction(self.action_save)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.action_exit)
        self.menu_edit.addAction(self.action_preferences)
        self.menu_view.addAction(self.action_zoomIn)
        self.menu_view.addAction(self.action_zoomOut)
        self.menu_view.addAction(self.action_fitToWindow)
        self.menu_tools.addAction(self.action_train)
        self.menu_tools.addAction(self.action_inference)
        self.menu_help.addAction(self.action_about)
        self.toolBar.addAction(self.action_open)
        self.toolBar.addAction(self.action_save)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.action_zoomIn)
        self.toolBar.addAction(self.action_zoomOut)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.action_train)
        self.toolBar.addAction(self.action_inference)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.action_detailView)
        self.toolBar.addAction(self.action_gridView)

        self.retranslateUi(MainWindow)
        self.slider_opacity.valueChanged.connect(self.label_opacityValue.setNum)

        self.tabWidget_tasks.setCurrentIndex(0)
        self.tabWidget_bottom.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"\u9065\u611f\u5f71\u50cf\u5206\u5272\u7cfb\u7edf", None))
        self.action_open.setText(QCoreApplication.translate("MainWindow", u"\u6253\u5f00", None))
#if QT_CONFIG(shortcut)
        self.action_open.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.action_save.setText(QCoreApplication.translate("MainWindow", u"\u4fdd\u5b58", None))
#if QT_CONFIG(shortcut)
        self.action_save.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+S", None))
#endif // QT_CONFIG(shortcut)
        self.action_exit.setText(QCoreApplication.translate("MainWindow", u"\u9000\u51fa", None))
#if QT_CONFIG(shortcut)
        self.action_exit.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+Q", None))
#endif // QT_CONFIG(shortcut)
        self.action_preferences.setText(QCoreApplication.translate("MainWindow", u"\u9996\u9009\u9879", None))
        self.action_zoomIn.setText(QCoreApplication.translate("MainWindow", u"\u653e\u5927", None))
#if QT_CONFIG(shortcut)
        self.action_zoomIn.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl++", None))
#endif // QT_CONFIG(shortcut)
        self.action_zoomOut.setText(QCoreApplication.translate("MainWindow", u"\u7f29\u5c0f", None))
#if QT_CONFIG(shortcut)
        self.action_zoomOut.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+-", None))
#endif // QT_CONFIG(shortcut)
        self.action_fitToWindow.setText(QCoreApplication.translate("MainWindow", u"\u9002\u5e94\u7a97\u53e3", None))
#if QT_CONFIG(shortcut)
        self.action_fitToWindow.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+0", None))
#endif // QT_CONFIG(shortcut)
        self.action_train.setText(QCoreApplication.translate("MainWindow", u"\u8bad\u7ec3", None))
#if QT_CONFIG(shortcut)
        self.action_train.setShortcut(QCoreApplication.translate("MainWindow", u"F5", None))
#endif // QT_CONFIG(shortcut)
        self.action_inference.setText(QCoreApplication.translate("MainWindow", u"\u63a8\u7406", None))
#if QT_CONFIG(shortcut)
        self.action_inference.setShortcut(QCoreApplication.translate("MainWindow", u"F6", None))
#endif // QT_CONFIG(shortcut)
        self.action_about.setText(QCoreApplication.translate("MainWindow", u"\u5173\u4e8e", None))
        self.action_detailView.setText(QCoreApplication.translate("MainWindow", u"\u8be6\u60c5\u89c6\u56fe (Detail)", None))
        self.action_gridView.setText(QCoreApplication.translate("MainWindow", u"\u7f51\u683c\u89c6\u56fe (Grid)", None))
        self.groupBox_dataSource.setTitle(QCoreApplication.translate("MainWindow", u"\u6570\u636e\u6e90\u7ba1\u7406 (Data Source Manager)", None))
        self.pushButton_addSample.setText(QCoreApplication.translate("MainWindow", u"\u6dfb\u52a0\u6837\u672c", None))
        self.groupBox_layerControl.setTitle(QCoreApplication.translate("MainWindow", u"\u56fe\u5c42\u63a7\u5236 (Layer Control)", None))
        self.checkBox_overlayPrediction.setText(QCoreApplication.translate("MainWindow", u"Overlay Prediction", None))
        self.checkBox_baseImage.setText(QCoreApplication.translate("MainWindow", u"Base Image (RGB/False Color)", None))
        self.checkBox_labelOnly.setText(QCoreApplication.translate("MainWindow", u"Label Only", None))
        self.label_opacity.setText(QCoreApplication.translate("MainWindow", u"Opacity:", None))
        self.label_opacityValue.setText(QCoreApplication.translate("MainWindow", u"70%", None))
        self.checkBox_swipeCompare.setText(QCoreApplication.translate("MainWindow", u"\u5377\u5e18\u5bf9\u6bd4 (Swipe Compare)", None))
        self.label_swipe.setText(QCoreApplication.translate("MainWindow", u"Position:", None))
        self.label_swipeValue.setText(QCoreApplication.translate("MainWindow", u"50%", None))
        
        # Tab 1: 数据洞察（使用可折叠面板，标题在组件中设置）
        self.tabWidget_contextControl.setTabText(self.tabWidget_contextControl.indexOf(self.tab_dataProfile), QCoreApplication.translate("MainWindow", u"\u6570\u636e\u6d1e\u5bdf (Data Profile)", None))
        # widget_datasetOverview, widget_classDistribution, widget_coverageAnalysis, widget_healthCheck 使用自定义组件，无需设置文本
        
        # Tab 2: 任务配置
        self.tabWidget_contextControl.setTabText(self.tabWidget_contextControl.indexOf(self.tab_taskConfig), QCoreApplication.translate("MainWindow", u"\u4efb\u52a1\u914d\u7f6e (Task Config)", None))
        self.groupBox_taskType.setTitle(QCoreApplication.translate("MainWindow", u"\u4efb\u52a1\u7c7b\u578b (Task Type)", None))
        self.label_trainInfo.setText(QCoreApplication.translate("MainWindow", u"\u8bad\u7ec3\u6a21\u5f0f\u914d\u7f6e", None))
        self.tabWidget_tasks.setTabText(self.tabWidget_tasks.indexOf(self.tab_train), QCoreApplication.translate("MainWindow", u"\u8bad\u7ec3 (Train)", None))
        self.label_inferenceInfo.setText(QCoreApplication.translate("MainWindow", u"\u63a8\u7406\u6a21\u5f0f\u914d\u7f6e", None))
        self.tabWidget_tasks.setTabText(self.tabWidget_tasks.indexOf(self.tab_inference), QCoreApplication.translate("MainWindow", u"\u63a8\u7406 (Inference)", None))
        self.groupBox_paramConfig.setTitle(QCoreApplication.translate("MainWindow", u"\u53c2\u6570\u914d\u7f6e (Parameter Config)", None))
        self.label_paramPlaceholder.setText(QCoreApplication.translate("MainWindow", u"\u53c2\u6570\u914d\u7f6e\u533a\u57df\n"
"(\u52a8\u6001\u52a0\u8f7d\u53c2\u6570\u63a7\u4ef6)", None))
        self.groupBox_actions.setTitle(QCoreApplication.translate("MainWindow", u"\u64cd\u4f5c\u6309\u94ae (Action Buttons)", None))
        self.pushButton_run.setText(QCoreApplication.translate("MainWindow", u"\u8fd0\u884c (Run)", None))
        self.pushButton_stop.setText(QCoreApplication.translate("MainWindow", u"\u505c\u6b62 (Stop)", None))
        self.pushButton_export.setText(QCoreApplication.translate("MainWindow", u"\u5bfc\u51fa (Export)", None))
        
        # Tab 3: 推理可视化
        self.tabWidget_contextControl.setTabText(self.tabWidget_contextControl.indexOf(self.tab_inferenceVis), QCoreApplication.translate("MainWindow", u"\u63a8\u7406\u53ef\u89c6\u5316 (Inference)", None))
        # inference_panel 使用自定义组件，内部已设置文本
        
        self.tabWidget_bottom.setTabText(self.tabWidget_bottom.indexOf(self.tab_logs), QCoreApplication.translate("MainWindow", u"\u65e5\u5fd7\u8f93\u51fa (Logs)", None))
        self.label_metricsPlaceholder.setText(QCoreApplication.translate("MainWindow", u"\u5b9e\u65f6\u8bad\u7ec3\u6307\u6807\u66f2\u7ebf\u663e\u793a\u533a\u57df\n"
"(\u53ef\u4f7f\u7528 matplotlib \u6216 pyqtgraph)", None))
        self.tabWidget_bottom.setTabText(self.tabWidget_bottom.indexOf(self.tab_metrics), QCoreApplication.translate("MainWindow", u"\u8bad\u7ec3\u6307\u6807 (Metrics)", None))
        self.label_progressInfo.setText(QCoreApplication.translate("MainWindow", u"\u5f53\u524d\u4efb\u52a1\u8fdb\u5ea6\uff1a", None))
        self.tabWidget_bottom.setTabText(self.tabWidget_bottom.indexOf(self.tab_progress), QCoreApplication.translate("MainWindow", u"\u8fdb\u5ea6 (Progress)", None))
        self.menu_file.setTitle(QCoreApplication.translate("MainWindow", u"\u6587\u4ef6 (&F)", None))
        self.menu_edit.setTitle(QCoreApplication.translate("MainWindow", u"\u7f16\u8f91 (&E)", None))
        self.menu_view.setTitle(QCoreApplication.translate("MainWindow", u"\u89c6\u56fe (&V)", None))
        self.menu_tools.setTitle(QCoreApplication.translate("MainWindow", u"\u5de5\u5177 (&T)", None))
        self.menu_help.setTitle(QCoreApplication.translate("MainWindow", u"\u5e2e\u52a9 (&H)", None))
        self.toolBar.setWindowTitle(QCoreApplication.translate("MainWindow", u"\u5de5\u5177\u680f", None))
    # retranslateUi

