# 🚀 任务配置高级参数模块路线图 (Task Config Advanced Params Roadmap)

## 📌 当前上下文
本项目已实现了模型选择 (`ModelSelectionWidget`)、数据智能推荐 (`AdvisorConfigWidget`) 和基础训练超参数 (`HyperparamTabsWidget`)。
在 `main_frame_ui.py` 中，`Tab 2: 任务配置` 页面预留了 `groupBox_paramConfig`（参数配置）作为动态高级参数的占位区。
本路线图旨在指导该占位区域的后续开发，实现以 `mmseg_params.py` 为基础的动态参数配置界面，满足专家用户的微调需求。

---

## 🗺️ Phase 1: 高级配置组件架构与重构 (Architecture & Components)
**目标**：重构现有的 `ConfigEditor` 组件，使其能无缝内嵌至主面板，并支持类别折叠与属性解析。

- [ ] **Task 1.1: 抽取并强化 `ParamRow` 组件**
  - **位置**: `ui/widgets/custom_widgets.py`
  - 增强 `ParamRow`，支持更多的参数类型验证（如类型校验错误时边框高亮）。
  - 为 `label` 或输入框增加一个可选的“受控/只读”模式，配合锁形图标，用于当参数被推荐引擎接管时使用。

- [ ] **Task 1.2: 改造 `ConfigEditor` 为内嵌组件**
  - **位置**: `config/config_editor.py` -> 重构至 `ui/widgets/advanced_config_widget.py`
  - 移除原有的独立导出 (Export/Reset) 底栏逻辑，改为提供 `get_params()` 与 `set_params()` 方法。
  - 使用 `CollapsibleBox` 加载 `mmseg_params.py` 定义的配置树：
    1. Model 配置区 (Backbone, Decode Head 等深层逻辑)
    2. Remote Sensing Data 配置区 (Crop Size, Channels, Mask/Ignore Index)
    3. Advanced Runtime 配置区 (Hooks, Logger Interval 等)

---

## 🗺️ Phase 2: “高级/专家模式” 交互设计 (Expert Mode Interaction)
**目标**：为复杂参数界面添加开关，避免惊吓普通用户，并解决基础超参数与高级配置间可能存在的重叠。

- [ ] **Task 2.1: 界面切换开关 (Toggle Switch)**
  - **位置**: `main_frame_ui.py` (在 `groupBox_paramConfig` 顶部)
  - 添加“开启高级配置选项 (Enable Advanced Settings)” 拨动开关或复选框。
  - 默认为关闭状态，仅当开启时展开底部的 `AdvancedConfigWidget`。

- [ ] **Task 2.2: 自定义 JSON 覆写区 (Custom Overrides Editor)**
  - 在 `AdvancedConfigWidget` 底部添加一个“底层字典覆写 (Dictionary Overrides)”区域。
  - 核心控件: `QPlainTextEdit`。
  - 允许用户手写类似 `{"model.decode_head.dropout_ratio": 0.2}` 的 JSON 片段以强制覆盖参数，供重度调试使用。

---

## 🗺️ Phase 3: 多源数据链路合并 (Data Pipeline & Synchronization)
**目标**：处理 ConfigAdvisor、基础面板、高级面板的数据融合冲突，构建生成最终训练配置字典的单点聚合逻辑。

- [ ] **Task 3.1: 状态感知与数据接管 (State Override & Awareness)**
  - 逻辑：当点击 `[应用推荐训练配置]` 按钮时（数据源自 `AdvisorConfigWidget`）：
    - `AdvancedConfigWidget` 中的对应控件（如 `input_channels`、`crop_size`）应自动填入推荐值。
    - 并且将这些控件转换为**半锁定状态 (只读且高亮显示)**，附带 tooltips：“受数据洞察推荐锁定”。
  - 当用户在 `ModelSelectionWidget` 中切换了 Backbone 时，应清空或重置 `AdvancedConfigWidget` 中关联的模型组件配置。

- [ ] **Task 3.2: 聚合器实现 (Config Aggregator)**
  - **位置**: `core/config_aggregator.py` 或集成在 `MMSegTrainer` 之前。
  - 定义合并策略 (Override Hierarchy):
    1. **最低优先级**: `mmseg_params.py` 默认值 (提取自 Advanced Config)。
    2. **中低优先级**: 原生 `AdvancedConfigWidget` 面板用户修改的值。
    3. **中高优先级**: 基础 `HyperparamTabsWidget` (例如通过 UI 明确配置的 LR、Optimizer)。
    4. **高优先级**: 智能推荐 `AdvisorConfigWidget` 中勾选启用的强制项。
    5. **最高优先级**: 自定义 JSON 覆写的纯文本参数。
  - 最终导出一个干净的 `dict`，供后续转换为 `.py` mmseg 配置文件。

---

## 🛠️ 后续执行建议 (Execution Notes)
1. **小步快跑**: 先完成 Task 1.2 将 `mmseg_params.py` 成功渲染在主界面占位区域，跑通 `get_params()` 获取全量字典。
2. **渐进增强**: JSON 覆写功能 (Task 2.2) 可以在最后加入。
3. **隔离数据流**: 遵循单向数据流原则，永远是上层 Controller 获取各组件字典后合并，尽量避免各同级 Widget 互相推拉数据（而是通过全局事件触发状态刷新）。
