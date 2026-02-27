# 🚀 训练配置模块开发路线图 (Training Config Roadmap)

## 📌 当前上下文
本路线图用于指导"任务配置"模块的开发。该模块实现从「数据洞察 → 配置推荐 → 训练执行 → 实时监控」的完整链路。
架构分为三层：框架适配层、核心逻辑层、UI展示层。

---

## 🗺️ Phase 1: 框架适配层 (Framework Adapter Layer)
**目标**：构建底层的配置生成器和训练执行器。

- [x] **Task 1.1: 定义基础适配器接口**
  - 文件: `core/framework_adapters/base_trainer.py`
  - 使用 `abc` 模块定义 `BaseTrainer` 抽象类
  - 抽象方法: `generate_config`, `start_training`, `stop_training`, `parse_log_line`

- [x] **Task 1.2: 实现 MMSegmentation 适配器**
  - 文件: `core/framework_adapters/mmseg_trainer.py`
  - `MMSegTrainer(BaseTrainer)` 实现
  - 使用 `mmengine.Config` + `subprocess.Popen`

---

## 🗺️ Phase 2: 核心逻辑层 (Core Logic Layer)
**目标**：将数据洞察转化为推荐参数，管理训练子进程。

- [x] **Task 2.1: ConfigAdvisor 增量扩展**
  - 文件: `core/config_advisor.py` (增量修改)
  - 新增 `recommend_rs_params()` 方法

- [x] **Task 2.2: 异步任务调度器**
  - 文件: `core/training_dispatcher.py`
  - `TrainingThread(QThread)` + PySide6 Signal

---

## 🗺️ Phase 3: UI展示层 - 配置区
**目标**：Supervisely 风格的多 Tab 参数配置界面。

- [x] **Task 3.1: 框架与模型选择区**
  - 文件: `ui/widgets/model_selection_widget.py`
- [x] **Task 3.2: 数据智能推荐区**
  - 文件: `ui/widgets/advisor_config_widget.py`
- [x] **Task 3.3: 训练超参数区**
  - 文件: `ui/widgets/hyperparam_tabs_widget.py`

---

## 🗺️ Phase 4: UI展示层 - 监控与集成
**目标**：实时图表绘制与顶层面板组装。

- [x] **Task 4.1: 实时监控看板**
  - 文件: `ui/widgets/training_monitor_widget.py`
- [x] **Task 4.2: 顶层面板集成与事件绑定**
  - 文件: `ui/training_panel.py`

---

## 🛠️ 编码规范
1. 框架统一使用 **PySide6**（非 PyQt5）
2. 适配器模式：训练器与推理器平行独立
3. ConfigAdvisor 增量扩展，不重写
