# Tab1「数据洞察」改进方案

> 基于 `TAB1_ISSUE_CHECKLIST.md` 中标记为"需要修改"的 9 项 + `BUG_REPORT.md` 中 Tab1 相关的 3 项 Bug，按依赖关系和逻辑分组划分为 5 个 Phase。

> ✅ **实施状态：Phase 1~5 已全部完成** (2026-05-20)

---

## 待修改项汇总

| 编号 | 问题 | Phase | 来源 | 状态 |
|------|------|-------|------|------|
| P0-1 | 按钮改名 + 错误弹窗增加格式说明 | Phase 1 | ISSUE_CHECKLIST | ✅ 已完成 |
| P1-3 | 分析进度条增加「取消」按钮 | Phase 1 | ISSUE_CHECKLIST | ✅ 已完成 |
| P1-10 | 覆盖率分析面板增加说明文字 | Phase 1 | ISSUE_CHECKLIST | ✅ 已完成 |
| P2-3 | 类别分布控制栏补充 Tooltip | Phase 1 | ISSUE_CHECKLIST | ✅ 已完成（改用常驻说明文字） |
| **A-01** | **Total Samples 数量计算错误（未去重）** | **Phase 2** | **BUG_REPORT** | ✅ 已完成 |
| P1-7 | 健康检查 Auto-Fix / Re-scan 信号连接 | Phase 2 | ISSUE_CHECKLIST | ✅ 已完成 |
| P1-8 | Resplit 后重置分析状态并重新触发 | Phase 2 | ISSUE_CHECKLIST | ✅ 已完成 |
| **D-02** | **切换图片时显示状态不一致（Overlay 勾选状态与渲染脱节）** | **Phase 2** | **BUG_REPORT** | ✅ 已完成 |
| P2-6 | Resplit 对话框确保显示真实样本数据 | Phase 2 | ISSUE_CHECKLIST | ✅ 已完成 |
| P1-5 | 类别分布图表支持类别名称映射 | Phase 3 | ISSUE_CHECKLIST | ⏭️ 跳过（保留原始） |
| P1-6 | "计算权重"结果联动到 Tab2 任务配置 | Phase 4 | ISSUE_CHECKLIST | ✅ 已完成 |
| **D-01** | **无法获知波段数量，缺少波段选择显示功能** | **Phase 5** | **BUG_REPORT** | ✅ 已完成 |

> **暂不纳入本轮**：A-02（Resplit 防重复校验，标记"暂不修改"）

---

## Phase 1 — UI 文案与微交互修复

**目标**：修复文案歧义、补全缺失的 Tooltip/说明文字、增加取消按钮。
**特点**：改动范围小、无逻辑依赖、可独立验证。

### 1.1 P0-1：按钮改名 + 错误弹窗优化

**涉及文件**：`ui/widgets/sidebar_widgets.py`（按钮文字）、`scripts/data_source_tree_example.py`（错误弹窗）

**改动内容**：
- 将 `pushButton_addSample` 的文字从 `"添加样本"` 改为 `"📂 加载数据集"`
- 为该按钮增加 Tooltip：`"选择 VOC 格式数据集根目录（需包含 JPEGImages、SegmentationClass、ImageSets 目录）"`
- `_validate_voc_structure()` 失败时的错误弹窗，在末尾追加一段帮助文字：
  ```
  💡 提示：如果您的数据不是 VOC 格式，请先将其转换为以下结构再加载。
  详细说明请参考项目文档。
  ```

### 1.2 P1-3：分析进度条增加「取消」按钮

**涉及文件**：`ui/analysis_panel.py`

**改动内容**：
- 在 `AnalysisControlWidget` 的 `progress_page` 中，进度条下方增加一个 `QPushButton("✕ 取消分析")`
- 该按钮点击后触发新信号 `cancel_clicked`
- `AnalysisPanel._connect_signals()` 中连接：`self.control_widget.cancel_clicked.connect(self.stop_analysis)`
- `stop_analysis()` 已有实现，无需修改核心逻辑

### 1.3 P1-10：覆盖率分析面板增加说明文字

**涉及文件**：`ui/widgets/coverage_analysis_widget.py`

**改动内容**：
- 在 `CoverageAnalysisCard._setup_ui()` 的图例上方，增加一行 `QLabel`：
  ```
  "展示每个类别在单张图像中的像素占比分布，帮助发现稀疏样本或全图充满的异常样本"
  ```
- 样式：`font-size: 10px; color: gray;`，与其他面板的说明文字风格一致

### 1.4 P2-3：类别分布控制栏补充 Tooltip

**涉及文件**：`ui/widgets/class_distribution_widget.py`

**改动内容**：
- `radio_pixel.setToolTip("按像素总数统计各类别分布")`
- `radio_image.setToolTip("按包含该类别的图像数量统计")`
- `check_log.setToolTip("使用对数坐标，适合类别间差异极大的情况")`
- `check_hide_bg` 已有 Tooltip，无需修改

> ✅ **已修复**（2026-05-20）：由于控件尺寸过小导致 Tooltip 不可见，改为添加常驻说明 QLabel：
> `"Px=像素统计 | Img=图像数 | Log=对数坐标 | NoBG=隐藏背景"`

---

## Phase 2 — 信号断链修复与数据联动

**目标**：修复已有 UI 但信号未连接的功能，确保 Resplit 后数据一致性，修复数据统计错误和显示状态同步问题。
**特点**：涉及 MainWindow 信号编排层，需注意信号重复连接问题。

### 2.0 A-01（BUG_REPORT）：Total Samples 数量计算错误（🔴 P0 必须修复）

**涉及文件**：`scripts/data_source_tree_example.py`（`_update_dataset_overview`）、`ui/widgets/dataset_overview_widget.py`（`update_data`）

**问题描述**：
当同一样本 ID 同时出现在 `val.txt` 和 `test.txt` 中时，`_update_dataset_overview()` 直接累加 `train_count + val_count + test_count`，导致 Total Samples 虚高。

**改动内容**：
- 在 `_update_dataset_overview()` 中计算总数时取并集去重：
  ```python
  train_samples = self.data_manager.get_samples('train')
  val_samples = self.data_manager.get_samples('val')
  test_samples = self.data_manager.get_samples('test')
  unique_total = len(set(train_samples) | set(val_samples) | set(test_samples))
  ```
- `DatasetOverviewWidget.update_data()` 增加可选参数 `unique_total`，当提供时显示去重后的总数
- UI 中以注释说明：「Train/Val/Test 各自独立计数，总数为去重后唯一样本数」

**⚠️ 注意**：保持各分集独立计数不变（Resplit 按钮的 enable/disable 判断依赖 `train + val + test > 0`），仅在"总数"显示处使用去重值。

### 2.0b D-02（BUG_REPORT）：切换图片时显示状态不一致（🟠 P1）

**涉及文件**：`scripts/data_source_tree_example.py`（图像切换回调）、`ui/widgets/sidebar_widgets.py`

**问题描述**：
取消勾选「Overlay Prediction」后，点击图层列表切换至另一张图像，新图仍以叠加预测掩膜的形式渲染。UI 控件状态与实际渲染行为脱节。

**改动内容**：
- 在图像切换渲染回调（`on_tree_item_changed` / `load_sample_visualization` 等）中，每次重新读取以下控件的当前状态：
  - `checkBox_overlayPrediction.isChecked()`
  - `checkBox_baseImage.isChecked()`
  - `checkBox_labelOnly.isChecked()`
- 确保渲染参数以 UI 控件当前值为准，而非使用上次推理时缓存的显示参数
- 修复后需同步测试三种模式（仅底图 / 仅标签 / 叠加预测）的切换一致性

### 2.1 P1-7：健康检查 Auto-Fix / Re-scan 信号连接

**涉及文件**：`scripts/data_source_tree_example.py`

**改动内容**：
- 在 `_connect_signals()` 中增加：
  ```python
  self.ui.widget_healthCheck.rescanRequested.connect(self._on_health_rescan)
  self.ui.widget_healthCheck.autoFixRequested.connect(self._on_health_autofix)
  ```
- 新增 `_on_health_rescan()` 方法：
  - 调用 `self._initialize_analysis_panel(self._current_data_root)` 重新触发分析
- 暂时去除“auto-fix”功能按钮及对应的代码 。

### 2.2 P1-8：Resplit 后重置分析状态并重新触发

**涉及文件**：`scripts/data_source_tree_example.py`

**改动内容**：
- 在 `_perform_resplit()` 方法末尾（`QMessageBox.information` 之后）追加：
  ```python
  # 重置分析状态并重新触发
  self.ui.analysis_panel.stop_analysis()  # 停止可能正在运行的旧任务
  self._initialize_analysis_panel(self._current_data_root)
  ```
- 同时修复 `_initialize_analysis_panel()` 中的信号重复连接问题：
  ```python
  # 使用 try/except 先断开旧连接
  try:
      self.ui.analysis_panel.analysis_started.disconnect(self._on_analysis_started)
      self.ui.analysis_panel.analysis_finished.disconnect(self._on_analysis_finished)
      self.ui.analysis_panel.analysis_error.disconnect(self._on_analysis_error)
  except RuntimeError:
      pass
  # 再重新连接
  self.ui.analysis_panel.analysis_started.connect(self._on_analysis_started)
  ...
  ```

### 2.3 P2-6：Resplit 对话框确保显示真实样本数据

**涉及文件**：`ui/widgets/dataset_resplit_dialog.py`

**改动内容**：
- 将 `set_sample_data()` 的调用时机提前：在 `__init__()` 中接收 `sample_data` 参数，在 `_setup_ui()` → `_create_select_mode_page()` → `_init_available_samples()` 之前设置好 `self.real_sample_data`
- 修改构造函数签名：
  ```python
  def __init__(self, current_train=0, current_val=0, current_test=0,
               train_samples=None, val_samples=None, test_samples=None, parent=None):
  ```
- 在 `MainWindow.on_resplit_dataset()` 中调整调用顺序，将样本数据直接传入构造函数

---

## Phase 3 — 类别名称映射

**目标**：让图表中的 C0/C1 显示为用户可理解的地物名称。
**特点**：需要新增 UI 组件和数据流，改动面较大。

### 3.1 P1-5：类别名称映射支持

**涉及文件**：
- `ui/widgets/class_distribution_widget.py`（消费映射数据）
- `ui/widgets/coverage_analysis_widget.py`（消费映射数据）
- `scripts/data_source_tree_example.py`（编排映射数据流）

**改动内容**：

保留原始，不修改

---

## Phase 4 — 计算权重联动 Tab2

**目标**：让"计算权重"按钮的结果能实际应用到训练配置中。
**特点**：跨 Tab 数据流，需要 Tab2 侧配合接收。

### 4.1 P1-6："计算权重"结果联动到 Tab2

**涉及文件**：`scripts/data_source_tree_example.py`、`ui/widgets/hyperparam_tabs_widget.py`

**改动内容**：

**Step A — 连接信号**
- 在 `_connect_signals()` 中：
  ```python
  self.ui.widget_classDistribution.weightsCalculated.connect(self._on_weights_calculated)
  ```

**Step B — 处理方法**
- 新增 `_on_weights_calculated(self, weights: list)` 方法：
  ```python
  def _on_weights_calculated(self, weights):
      # 弹出确认对话框
      msg = f"已计算类别权重（Median Frequency Balancing）:\n{weights}\n\n是否应用到任务配置？"
      reply = QMessageBox.question(self, "类别权重", msg,
                                    QMessageBox.Yes | QMessageBox.No)
      if reply == QMessageBox.Yes:
          self.ui.widget_hyperparamTabs.set_class_weights(weights)
          self._log_to_bottom("✅ 类别权重已应用到任务配置")
  ```

**Step C — Tab2 侧接收**
- `HyperparamTabsWidget` 增加 `set_class_weights(weights)` 方法，将权重填入对应的 UI 控件（如 class_weight 复选框勾选 + 权重值列表填入）

---

## Phase 5 — 影像波段信息与波段选择（来自 BUG_REPORT D-01）

**目标**：让用户能获知当前数据集的波段数量，并自由选择显示波段组合。
**特点**：涉及图像读取层和侧边栏 UI，需要 GDAL 支持多波段读取。

### 5.1 D-01（BUG_REPORT）：无法获知波段数量，缺少波段选择功能（🟠 P1）

**涉及文件**：`ui/widgets/sidebar_widgets.py`、`ui/widgets/smart_canvas.py`（`DynamicImageReader`）

**问题描述**：
加载多波段遥感影像（如 4 波段 RGBNIR）后，主视图固定以前三波段（RGB）渲染，无任何波段信息提示，用户无法自定义显示波段组合（如近红外假彩色合成）。

**改动内容**：

**Step A — 波段信息读取**
- 在 `DynamicImageReader` 图像加载时，通过 GDAL `RasterCount` 接口获取波段数并缓存
- 若 GDAL 不可用，fallback 到 PIL 读取（仅支持 RGB，波段数固定为 3）

**Step B — 侧边栏增加波段映射控件**
- 在 `SampleManagementSidebar` 或图层控制区增加「波段映射」下拉选择器：
  - R 通道 → 第 ? 波段
  - G 通道 → 第 ? 波段
  - B 通道 → 第 ? 波段
- 提供常用预设：`RGB (1,2,3)`、`NIR假彩色 (4,3,2)`、`SWIR (5,4,3)` 等
- 当图像波段数 ≤ 3 时，控件自动禁用并显示"当前图像为 RGB 三波段"

**Step C — 波段信息展示**
- 在图像信息区（状态栏或侧边栏）显示当前图像的波段数量
- 格式示例：`波段: 4 (当前显示: R=3, G=2, B=1)`

**⚠️ 注意**：
- GDAL 为可选依赖，不可用时需优雅降级
- 波段切换后需重新渲染主视图画布，注意性能（大图场景）

> ✅ **已修复**（2026-05-20）：
> 1. SpinBox 宽度从 40px 加宽至 50px，并添加 Tooltip
> 2. `DynamicImageReader._read_raster_display_data()` 新增 `band_indices` 参数，`SmartCanvas.set_band_mapping()` 实现按用户选择波段重新渲染
> 3. 去掉"预设:"QLabel，改为 ComboBox 自带 Tooltip 说明

---

## 实施顺序与依赖关系

```
Phase 1 (UI文案/微交互)     ← 无依赖，可立即开始
    ↓
Phase 2 (信号断链/数据联动/Bug修复)  ← 依赖 Phase 1 中的取消按钮（P1-3）已就位
    ↓
Phase 3 (类别名称映射)       ← 依赖 Phase 2 完成后分析数据流稳定
    ↓
Phase 4 (权重联动 Tab2)      ← 依赖 Phase 3 的类别映射（权重对话框可显示类别名称）
    ↓
Phase 5 (波段信息与选择)     ← 独立功能，可与 Phase 3/4 并行
```

---

## 工作量估算

| Phase | 改动项数 | 涉及文件数 | 预估工作量 |
|-------|---------|-----------|-----------|
| Phase 1 | 4 项 | 3 个文件 | **XS**（纯文案/Tooltip/单按钮） |
| Phase 2 | 5 项 | 3 个文件 | **S-M**（信号连接 + 方法实现 + 去重逻辑 + 状态同步） |
| Phase 3 | 1 项 | 3 个文件 + 1 新文件 | **M**（新对话框 + 数据流 + 持久化） |
| Phase 4 | 1 项 | 2 个文件 | **S**（信号连接 + 跨 Tab 方法调用） |
| Phase 5 | 1 项 | 2 个文件 | **M**（GDAL 波段读取 + 新 UI 控件） |

---

## ⚠️ 实施注意事项

1. **Phase 2 信号重复连接**：`_initialize_analysis_panel()` 必须先 disconnect 再 connect，否则每次加载数据集回调会翻倍触发
2. **Phase 2 Auto-Fix 安全性**：修改磁盘文件前必须弹确认框 + 自动备份原始文件到 `{data_root}/.backup/`
3. **Phase 2 Resplit 时序**：先 `stop_analysis()` 停止旧进程，再重新触发，避免多进程写同一 SQLite
4. **Phase 2 A-01 去重注意**：保持各分集独立计数不变（Resplit enable/disable 依赖 `train+val+test>0`），仅在"总数"显示处使用去重值
5. **Phase 2 D-02 状态同步**：修复后需同步测试 `checkBox_labelOnly` 与 `checkBox_baseImage` 两种模式的切换一致性
6. **Phase 3 持久化路径**：使用 `{data_root}/.rs_seg_gui/` 隐藏目录，避免污染用户数据集结构
7. **Phase 5 GDAL 依赖**：波段读取需要 GDAL/rasterio，当不可用时应 fallback 到 PIL 读取（仅支持 RGB），并在 UI 中提示"安装 GDAL 以支持多波段显示"
8. **架构原则**：所有改动遵循 Widget(UI) → MainWindow(信号编排) → Core(计算) 三层分离
