# 🚀 SegProject 开发路线图 (AI Vibe Coding Roadmap)

## 📌 当前上下文 (Context)
本项目是一个专业的遥感深度学习数据管理与推理辅助软件。基于 PySide6 (Qt) 开发。
当前重点：优化「数据洞察 (Data Profile)」Tab 的交互逻辑，增强列表的实用性，并打通“数据分析”与“训练配置”之间的数据链路。

---

## 🗺️ 阶段一：视图双向联动与体验打磨 (View Synchronization & Polish)
**当前进度**：已实现基础的 `GalleryWidget`（网格视图）、`DetailWidget`（详情视图）切换，以及缩略图的懒加载。
**本阶段目标**：打通左侧树状列表、右侧网格视图、以及详情视图之间的信号联动，实现丝滑的“宏观到微观”穿梭体验。

- [x] **任务 1.1: 列表与画廊的双向选择同步 (Two-Way Selection Sync)**
  - **逻辑 1 (Left -> Right):** 当用户在左侧 `数据源管理` (QTreeView/QListWidget) 单击选中某个样本时，右侧画廊应自动滚动到对应缩略图，并设置为高亮选中状态。
  - **逻辑 2 (Right -> Left):** 当用户在右侧画廊 (Gallery) 单击选中某张缩略图时，左侧树状列表应自动展开对应文件夹，并高亮该文件项。
  - *注意：使用信号屏蔽 (BlockSignals) 防止无限循环触发。*

- [x] **任务 1.2: 完善“画廊 -> 详情”的穿梭交互 (Macro to Micro Transition)**
  - 绑定右侧画廊的 `itemDoubleClicked` 信号。
  - 双击触发动作：
    1. 获取被双击图像的绝对路径。
    2. 自动触发顶部工具栏的“详情视图 (Detail)”切换逻辑。
    3. 调用 `SmartCanvas.load_layer()` 加载全分辨率底图和对应的预测结果/真值 Mask。

- [x] **任务 1.3: 顶部工具栏状态管理 (Toolbar State Awareness)**
  - 当处于“网格视图 (Grid)”时：禁用“放大/缩小”等只属于大图画布的专用工具按钮。
  - 当处于“详情视图 (Detail)”时：激活缩放工具。添加 `[ ⬅️ 返回画廊 ]` 快捷动作（可集成在工具栏左侧），点击后清空 `SmartCanvas` 以释放内存，并切回网格界面。

- [x] **任务 1.4: 缩略图缓存固化 (Thumbnail Cache Persistence - 性能兜底)**
  - *背景：虽然实现了懒加载，但每次滚动重新合成 Image + Mask 会消耗 CPU。*
  - 完善缓存机制：在后台异步生成缩略图时，将合成好的 `RGB + Mask` 结果直接存为 `.cache/thumb_xxx.jpg` 本地文件。
  - 画廊滚动时，懒加载只负责读取几 KB 的本地缓存图，确保滚动帧率稳定在 60fps 绝对不卡顿。

---

## 🗺️ 阶段二：增强样本列表的快捷交互 (Sample List Context Menu)
**目标**：在健康检查或数据过滤时，让用户能快速定位到硬盘上的错误样本文件。

- [x] **任务 2.1: 启用右键菜单**
  - 在左侧样本列表控件（`QListWidget` / `QTreeWidget`）上开启 `setContextMenuPolicy(Qt.CustomContextMenu)`。
  - 绑定 `customContextMenuRequested` 信号。
- [x] **任务 2.2: 实现右键动作**
  - 获取当前选中项的绝对路径。
  - 添加操作 1：`📋 复制文件名` (写入剪贴板)。
  - 添加操作 2：`🔗 复制完整路径` (写入剪贴板)。
  - 添加操作 3：`📂 在文件夹中显示 (Reveal in Explorer)`。
- [x] **任务 2.3: 跨平台文件管理器定位**
  - 编写独立的 helper 函数，实现跨平台的选中文件逻辑：
    - Windows: `explorer /select,"{path}"`
    - macOS: `open -R "{path}"`
    - Linux: `xdg-open "{dir_path}"`

---

## 🗺️ 阶段三：数据分析反哺训练配置 (Data-Driven Configuration)
**目标**：将“类别分布”和“覆盖率”等统计信息，转化为指导后续 MMSegmentation 模型训练的具体参数。

- [x] **任务 3.1: 定义数据结构 (`DatasetInsights`)**
  - 在 `core/` 目录下创建 Dataclass `DatasetInsights`。
  - 包含字段：类别名称、像素占比、建议权重 (`suggested_class_weights`)、空样本比例、小目标比例等。
- [x] **任务 3.2: 创建配置顾问 (`ConfigAdvisor`)**
  - 编写独立逻辑类 `ConfigAdvisor`，接收 `DatasetInsights` 对象。
  - 实现 `recommend_loss_config()`：若类别极度不平衡，生成带 class_weight 的 CrossEntropyLoss 或 FocalLoss 配置字典。
  - 实现 `recommend_augmentation()`：基于空样本/小目标比例，推荐如 `RandomCrop` 约束或 `CopyPaste` 的数据增强策略。
- [x] **任务 3.3: 预留 UI 联动接口**
  - 在主窗口或控制器中预留逻辑：当用户从“数据洞察”切换到“任务配置”时，实例化 `ConfigAdvisor`。
  - 提供 `[ 💡 应用推荐训练配置 ]` 按钮，自动将推荐的参数覆盖到右侧的配置表单中。

---

## 🛠️ 编码规范与约束 (Code Guidelines)
1. **纯净的 UI 逻辑**：不要在 UI 槽函数中写复杂的业务逻辑，严格遵循 MVC / 适配器模式（特别是阶段三）。
2. **性能优先**：处理大图必须使用 `rasterio` 降采样（Decimated Read）或显示缩略图。
3. **原生控件为主**：优先使用 Qt Native 属性（如 `setAutoRaise`）和 `qtawesome` 图标库，避免过度依赖繁杂的 QSS 样式表。