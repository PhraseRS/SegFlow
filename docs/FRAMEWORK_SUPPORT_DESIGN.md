# 框架支持体系 — 技术实现文档

> **版本**: v1.1（实现完成）
> **范围**: mmseg 框架支持、conda 环境检测、多框架扩展机制

---

## 1. 模块总览

| 模块 | 路径 | 职责 |
|------|------|------|
| 框架注册表 | `core/framework_registry.py` | 数据驱动的框架元数据注册，提供包列表/Trainer 类路径 |
| 异步环境探针 | `utils/env_check_worker.py` | QThread Worker，后台执行 subprocess 探针 |
| 环境状态管理器 | `core/env_state_manager.py` | QObject 单例，持有并广播环境就绪状态 |
| 环境配置 UI | `ui/widgets/env_config_widget.py` | 防抖自动验证、展示结果、发射 Signal |
| 模型选择 UI | `ui/widgets/model_selection_widget.py` | 从注册表动态读取框架列表，发射 `framework_changed` |
| 训练器基类 | `core/framework_adapters/base_trainer.py` | 抽象接口，含 `python_path` 参数 |
| MMSeg 训练器 | `core/framework_adapters/mmseg_trainer.py` | 使用目标解释器启动训练子进程 |
| 训练调度器 | `core/training_dispatcher.py` | QThread 包装，透传 `python_path` |
| 配置健康度 | `ui/widgets/task_config_dashboard.py` | 5 维度评分，含"环境就绪"维度 |
| Conda 枚举 | `utils/mmseg_env_manager.py` | conda env list + 同步探针（保留向后兼容） |

---

## 2. 架构图

```
┌─────────────────────────────────────────────────────────────┐
│              任务配置 Tab (右侧面板，自上而下)                  │
│                                                             │
│  ┌──────────────────────┐  配置区                           │
│  │  ModelSelectionWidget │  ← 框架/模型选择                  │
│  │  WeightSelection      │  ← 权重选择                      │
│  │  Advisor / Hyperparams│  ← 参数配置                      │
│  │  AdvancedConfig       │  ← 高级参数                      │
│  └──────────┬────────────┘                                  │
│             │ framework_changed(display_name, packages)      │
│  ┌──────────▼────────────┐  运行前检查区 (Preflight Check)   │
│  │  EnvConfigWidget      │  ← 环境准备状态                   │
│  │  - 启动 EnvCheckWorker│                                  │
│  │  - 显示 Loading / 结果│                                  │
│  └──────────┬────────────┘                                  │
│             │ env_ready / not_ready                          │
│  ┌──────────▼────────────┐  动作区                           │
│  │  Run / Stop / Export  │  ← 操作按钮                      │
│  └───────────────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
              ↓                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  EnvStateManager (QObject 单例)              │
│  state_changed Signal → ConfigHealthBar / 主控制器           │
└──────────┬──────────────────────────┬───────────────────────┘
           ↓                          ↓
┌──────────────────────┐   ┌──────────────────────────────────┐
│  FrameworkRegistry   │   │       EnvCheckWorker (QThread)   │
│  - FrameworkSpec     │   │  - _probe(): subprocess 探针     │
│  - required_packages │   │  - stderr 分离，取最后行 JSON    │
│  - trainer_class_path│   │  - check_finished Signal(dict)   │
└──────────────────────┘   └──────────────────────────────────┘
           ↓ load_trainer_class()
┌──────────────────────────────────────────────────────────────┐
│              BaseTrainer (ABC)                                │
│  start_training(config, work_dir, python_path=None)          │
│              ↓ 实现                                           │
│  MMSegTrainer._find_train_script(interpreter)                │
│  → 用目标解释器探测 mmseg 安装路径 → 启动 train.py           │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 核心流程

### 3.1 环境检测流程（防抖自动验证）

```
用户切换下拉 / 编辑路径
    ↓ _on_env_changed() / _on_custom_path_edited()
    ↓ 路径同步到输入框 + 失效缓存
    ↓ _schedule_auto_validate(800ms / 1200ms)
    ↓ [防抖定时器 QTimer.singleShot]
    ↓ 到期 → _auto_validate()
    ↓ 检查路径是否变化 & 是否已有缓存 → 跳过或继续
    ↓
validate_env():
    ↓ 禁用 Re-check 按钮，显示 Loading 状态
    ↓ 创建 EnvCheckWorker(python_path, required_packages)
    ↓ worker.start()
[后台线程] _probe():
    ↓ subprocess.check_output(python_path, "-c", probe_code)
    ↓ stderr=subprocess.PIPE（分离 warning）
    ↓ 取 stdout 最后一行 JSON 解析
    ↓ check_finished.emit(result)
[主线程] _on_check_finished(result):
    ↓ _parse_check_result → (is_valid, message)
    ↓ 更新 status_label（绿/红/蓝）
    ↓ EnvStateManager.instance().update(...)  → state_changed Signal
    ↓ env_ready / env_not_ready Signal
_on_check_worker_done():
    ↓ worker.deleteLater()
    ↓ self._check_worker = None
```

**触发条件与防抖时间**：

| 触发 | 防抖延迟 | 说明 |
|------|----------|------|
| 切换下拉列表 | 800ms | 快速切换时只验证最后一个 |
| 手动编辑输入框 | 1200ms | 等用户输入完毕 |
| 点击 "Re-check" | 0ms（立即） | 手动强制重新验证 |
| 验证进行中再次触发 | 取消旧 Worker | 启动新 Worker |

### 3.2 训练启动流程（python_path 传递链）

```
用户点击 "运行"
    ↓
主控制器._on_start_training()
    ↓ ensure_ready_for_training():
    │   ├─ 有缓存 → 直接返回缓存结果
    │   └─ 无缓存 → 自动执行同步验证（兜底，1-2s 可接受）
    ↓ 从 EnvStateManager.instance().python_path 获取解释器
    ↓ 回退：widget_envConfig.get_selected_python_path()
    ↓
TrainingThread(trainer, config_path, work_dir, python_path)
    ↓ run() → trainer.start_training(config, work_dir, python_path)
    ↓
MMSegTrainer.start_training():
    ↓ interpreter = python_path or sys.executable
    ↓ _find_train_script(interpreter):
    │   ├─ 用目标解释器探测 mmseg.__file__ 路径
    │   ├─ 尝试 .mim/tools/train.py（mim 安装）
    │   └─ 尝试 ../tools/train.py（源码安装）
    ↓ subprocess.Popen([interpreter, '-u', train_script, ...])
```

### 3.3 框架切换流程

```
用户在 ModelSelectionWidget 切换框架下拉
    ↓ framework_changed.emit(display_name, required_packages)
    ↓
EnvConfigWidget.set_framework(display_name, required_packages):
    ↓ 更新 self._required_packages
    ↓ 失效验证缓存
    ↓ 更新 framework_hint_label（显示所需包列表）
```

---

## 4. 关键实现细节

### 4.1 FrameworkRegistry (`core/framework_registry.py`)

```python
@dataclass
class FrameworkSpec:
    key: str                    # "mmseg"
    display_name: str           # "MMSegmentation"
    required_packages: List[str]  # ["torch", "mmcv", "mmseg"]
    trainer_class_path: str     # "core.framework_adapters.mmseg_trainer.MMSegTrainer"
    description: str = ""

FRAMEWORK_REGISTRY: Dict[str, FrameworkSpec] = {"mmseg": FrameworkSpec(...)}

# 便捷函数
get_all_display_names() → List[str]
get_key_by_display_name(name) → Optional[str]
get_required_packages(name) → List[str]
spec.load_trainer_class() → Type[BaseTrainer]  # 延迟 importlib 导入
```

### 4.2 EnvCheckWorker (`utils/env_check_worker.py`)

- 动态生成探针代码：根据 `required_packages` 列表拼接 `import xxx; res['details']['xxx'] = xxx.__version__`
- `stderr=subprocess.PIPE` 分离 warning，不污染 JSON
- 取 stdout **最后一行**非空内容作为 JSON（防止前面有 print 输出）
- 超时 15s，`JSONDecodeError` 时返回原始输出前 200 字符辅助排查

### 4.3 EnvStateManager (`core/env_state_manager.py`)

- 应用级单例：`EnvStateManager.instance()`
- `state_changed` Signal 广播完整快照 dict
- `ConfigHealthBar` 在构造时订阅，实时更新 env pill
- 主控制器训练启动时从 `EnvStateManager.python_path` 读取

### 4.4 EnvConfigWidget 交互模式

**面板位置**：位于任务配置 Tab 底部、操作按钮（Run/Stop/Export）正上方，作为"运行前检查区（Preflight Check）"。设计意图：用户从上到下完成配置后，自然下滑确认环境就绪，再点击运行。

**UI 布局**（精简后）：

```
┌─────────────────────────────────────────────────┐
│ Conda environments                    [Refresh] │
│ ┌─────────────────────────────────────────────┐ │
│ │ py38mm1x - D:\anaconda3\envs\...  ▼        │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│ Python executable                  [Re-check ↻] │
│ ┌─────────────────────────────────────────────┐ │
│ │ D:\anaconda3\envs\py38mm1x\python.exe       │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ ✅ Ready: Python 3.8 | Torch 2.4 | CUDA ✓  │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**已移除**：`Use Selected` 按钮、`summary_label`（冗余信息）

**核心行为**：

- 切换下拉 → 路径自动填入输入框 → 防抖 800ms → 自动验证
- 手动编辑输入框 → 防抖 1200ms → 自动验证
- "Re-check" 按钮 → 立即强制重新验证（安装新包后手动重试）
- `refresh_envs()`：内部创建轻量 `_RefreshWorker(QThread)` 执行 `conda env list`
- `validate_env()`：创建 `EnvCheckWorker`，连接 `check_finished` → `_on_check_finished`
- Worker 完成后通过 `_on_check_worker_done()` 调用 `deleteLater()` 并置 `self._check_worker = None`
- `ensure_ready_for_training()`：有缓存直接返回；无缓存自动执行同步验证（兜底）
- `_schedule_refresh()`：构造时用 `QTimer.singleShot(0, ...)` 延迟刷新

**状态标签颜色**：

| 状态 | 样式 |
|------|------|
| 未选择 | 灰底 |
| 验证中 | 蓝底 + "🔍 正在检测..." |
| 通过 | 绿底 + "✅ Ready: ..." |
| 失败 | 红底 + "❌ ..." / "⚠️ Incomplete: ..." |

### 4.5 ConfigHealthBar 5 维度评分

| 维度 | 分值 | 数据来源 |
|------|------|----------|
| 数据集就绪 | 20 | params.dataset_samples |
| 模型参数已选 | 20 | params.method / backbone |
| 显存估算 | 20 | crop_size² × in_ch × batch_size 计算 |
| 关键增强选项 | 20 | params.aug_random_flip 等 |
| 环境就绪 | 20 | EnvStateManager.is_ready |

总分归一化到 100 分，进度条颜色：≥75 绿 / ≥50 黄 / <50 红。

---

## 5. 扩展新框架指南

添加新框架（如 PaddleSeg）只需：

1. 在 `core/framework_registry.py` 的 `FRAMEWORK_REGISTRY` 中添加新条目
2. 实现 `core/framework_adapters/paddleseg_trainer.py`（继承 `BaseTrainer`）
3. 无需修改 UI 代码——`ModelSelectionWidget` 和 `EnvConfigWidget` 自动适配

---

## 6. 注意事项

### 线程安全

- Worker 线程内**严禁**直接操作 QWidget，所有结果通过 Signal/Slot 回到主线程
- Worker 完成后必须清理引用（`self._check_worker = None`），防止 `RuntimeError: Internal C++ object already deleted`

### 向后兼容

- `BaseTrainer.start_training()` 的 `python_path=None` 保持现有行为
- `MMSegEnvManager` 原有接口保留，`mmseg_env_manager.py` 文件名不变

### 同步/异步边界

| 操作 | 线程 | 方式 |
|------|------|------|
| conda env list | 后台 _RefreshWorker | QThread + Signal |
| Python 解释器探针 | 后台 EnvCheckWorker | QThread + Signal |
| UI 更新 | 主线程 | Signal/Slot 自动 marshal |
| 训练启动 | TrainingThread（已有） | 现有机制 |
| ensure_ready_for_training | 主线程 | 读缓存；无缓存时同步兜底验证 |

---

*文档结束*
