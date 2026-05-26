# Tab3「推理可视化」改进方案

> 基于 `TAB3_ISSUE_CHECKLIST.md` 中标记为"需要修改"的 6 项，按依赖关系和逻辑分组划分为 3 个 Phase。

> ✅ **实施状态：Phase 1~5 已全部完成** (2026-05-21)

---

## 待修改项汇总

| 编号 | 问题 | Phase | 状态 |
|------|------|-------|------|
| P1-7 | 删除重复的 `_on_inference_finished` 定义 | Phase 1 | ✅ 已完成 |
| P0-3 | 隐藏批量推理按钮 + 禁用批量模式 Radio Button | Phase 1 | ✅ 已完成 |
| P2-1 | 隐藏「置信度阈值」控件 | Phase 1 | ✅ 已完成（已回退为不隐藏） |
| P1-1 | 模型库下拉框空状态提示文字 | Phase 2 | ✅ 已完成 |
| P1-3 | 推理成功后去掉弹窗，改为状态栏非侵入提示 | Phase 2 | ✅ 已完成 |
| P1-2 | 推理策略增加像素尺寸阈值说明 + 选图后自动推荐 | Phase 3 | ✅ 已完成 |
| **NEW** | **去除右侧预览图 + 类别颜色配置保留右侧并连接GIS画布** | **Phase 4** | ✅ 已完成 |
| **NEW** | **背景类透明修复 + 推理结果区恢复可见 + 导出格式改为语义分割常用格式** | **Phase 5** | ✅ 已完成 |

---

## Phase 1 — 代码清理与 UI 隐藏

**目标**：消除残缺功能和无效控件，不涉及任何逻辑改动。
**特点**：零风险，纯删除/隐藏操作，可独立验证。

### 1.1 P1-7：删除重复的 `_on_inference_finished`

**涉及文件**：`scripts/data_source_tree_example.py`

**改动内容**：
- 删除 L2099-2107 的旧版简单回调（仅有状态栏更新和日志的版本）
- 保留 L2310 开始的完整版本（含 mask 注入、GIS 画布更新逻辑）
- 确认信号连接处（L510）只连接一次，无重复

### 1.2 P0-3：隐藏批量推理相关控件

**涉及文件**：`ui/inference_panel.py`

**改动内容**：
- 在 `_create_inference_strategy_group()` 中：
  ```python
  self.radioButton_batchInference.setVisible(False)
  ```
- 在 `_create_action_export_group()` 中：
  ```python
  self.pushButton_batchInference.setVisible(False)
  ```
- 确保 `radioButton_singleImage` 默认选中（已有，无需改动）

### 1.3 P2-1：隐藏「置信度阈值」控件

**涉及文件**：`ui/inference_panel.py`

**改动内容**：
- ~~在 `_create_inference_strategy_group()` 末尾隐藏控件~~
- `inference_params` 字典中保留 `conf_threshold` 键（避免下游代码 KeyError），值固定为默认值 `0.5`

> ✅ **已回退**（2026-05-20）：删除了 `setVisible(False)` 调用，恢复控件可见，并添加 Tooltip 说明。

---

## Phase 2 — 交互反馈改善

**目标**：修复两处对用户造成困惑的反馈问题。
**特点**：改动范围局限在 `inference_panel.py` 内，低风险。

### 2.1 P1-1：模型库下拉框空状态提示

**涉及文件**：`ui/inference_panel.py`

**改动内容**：
- 修改 `scan_trained_models()` 末尾逻辑：扫描结束后若 `comboBox_modelRegistry.count() == 1`（只有默认项），将默认项文字改为：
  ```
  （未找到训练记录，请先在 Tab1 加载数据集，或手动指定下方配置文件）
  ```
- 修改 `_manual_refresh_registry()` 中 `_current_data_root` 为空时的提示文字：
  ```
  ⚠️  请先在 Tab1 加载数据集，才能扫描已训练模型
  ```
- 为 `pushButton_refreshRegistry` 增加 Tooltip：
  ```
  需要先在 Tab1 加载数据集才能扫描 work_dirs 中的训练记录
  ```

### 2.2 P1-3：推理成功后去掉弹窗

**涉及文件**：`ui/inference_panel.py`

**改动内容**：

`_handle_inference_success()` 中：
- 删除普通推理完成时的 `QMessageBox.information(...)` 调用（L1574-1578）
- 替换为通过已有的 `_emit_log()` 写入底部日志，并通过 `inference_finished` 信号让 `MainWindow` 更新状态栏：
  ```python
  self._emit_log(f"✅ 推理完成：{os.path.basename(image_path)}，策略：{strategy}")
  if saved_path:
      self._emit_log(f"   预览已保存至：{saved_path}")
  ```
- **保留**大图分块推理完成时的弹窗（L1468-1476）：该场景耗时长，用户可能已切换操作，需主动通知

---

## Phase 3 — 推理策略智能引导

**目标**：P1-2，让用户在选择推理策略时有明确参考，并在选图后自动推荐。
**特点**：涉及选图回调逻辑，需注意不影响现有的 GIS 同步信号链路。

### 3.1 P1-2：策略说明文字 + 自动推荐

**涉及文件**：`ui/inference_panel.py`

**改动内容**：

**Step A — 替换策略说明文字**

将 `label_strategyNote` 的初始文字改为：
```
• 全图缩放：图像 ≤ 2000×2000 像素，快速预览
• 滑窗推理：图像 2000–20000 像素范围，标准推理
• 大图分块：图像 > 20000 像素超大影像（需 GDAL）
```

**Step B — 新增 `_auto_recommend_strategy(w, h)` 方法**

```python
def _auto_recommend_strategy(self, w: int, h: int):
    """根据图像尺寸自动推荐推理策略并更新说明文字"""
    if w * h <= 2000 * 2000:
        self.radioButton_resize.setChecked(True)
        tag = ("【推荐】", "", "")
    elif w * h <= 20000 * 20000:
        self.radioButton_slidingWindow.setChecked(True)
        tag = ("", "【推荐】", "")
    else:
        self.radioButton_largeImageBlock.setChecked(True)
        tag = ("", "", "【推荐】")

    self.label_strategyNote.setText(
        f"• 全图缩放 {tag[0]}：图像 ≤ 2000×2000 像素，快速预览\n"
        f"• 滑窗推理 {tag[1]}：图像 2000–20000 像素范围，标准推理\n"
        f"• 大图分块 {tag[2]}：图像 > 20000 像素超大影像（需 GDAL）"
    )
    self._emit_log(f"💡 已根据图像尺寸（{w}×{h}）自动推荐推理策略")
```

**Step C — 在 `_browse_input_image()` 中调用**

在单图模式选图成功、`lineEdit_inputPath.setText(file_path)` 之后追加：
```python
try:
    from PIL import Image as _PIL_Image
    with _PIL_Image.open(file_path) as _img:
        _w, _h = _img.size
    self._auto_recommend_strategy(_w, _h)
except Exception:
    pass  # 读取失败时静默跳过，不影响主流程
```

---

## 实施顺序与依赖关系

```
Phase 1（代码清理/UI隐藏）  ← 无依赖，立即可执行
    ↓
Phase 2（交互反馈改善）     ← 无依赖，可与 Phase 1 合并提交
    ↓
Phase 3（策略智能引导）     ← 依赖 Phase 1 中批量模式已隐藏（避免自动推荐误触发批量逻辑）
```

---

## 工作量估算

| Phase | 改动项数 | 涉及文件数 | 预估工作量 |
|-------|---------|-----------|-----------|
| Phase 1 | 3 项 | 2 个文件 | **XS**（纯删除/隐藏） |
| Phase 2 | 2 项 | 1 个文件 | **XS**（文字替换 + 删除弹窗） |
| Phase 3 | 1 项 | 1 个文件 | **S**（新增方法 + 回调注入） |
| Phase 4 | 1 项 | 2~3 个文件 | **M**（布局重构 + 控件迁移） |

---

## ⚠️ 实施注意事项

1. **Phase 1 删除重复函数**：删除前确认 L2099 版本没有被其他地方单独引用（全局搜索 `_on_inference_finished`）
2. **Phase 1 P2-1 回退**：需删除 `setVisible(False)` 调用，恢复置信度阈值控件可见
3. **Phase 2 保留大图弹窗**：大图分块推理耗时可能超过数分钟，完成弹窗是必要的主动通知，不应一并删除
4. **Phase 3 自动推荐不强制**：`_auto_recommend_strategy()` 只预选 Radio Button，用户仍可手动覆盖，不锁定选择
5. **Phase 3 GIS 同步不受影响**：`_browse_input_image()` 末尾的 `input_path_selected.emit()` 信号调用位置不变，自动推荐逻辑插入在其之前
6. **Phase 4 布局重构**：需仔细处理信号重连，确保颜色配置控件迁移后仍能正确驱动 GIS 画布渲染
7. **架构原则**：所有改动遵循 Widget(UI) → MainWindow(信号编排) → Core(计算) 三层分离

---

## Phase 4 — 推理结果展示重构（✅ 已完成）

**目标**：去除右侧推理结果区的预览图控件，类别颜色配置保留在右侧并连接 GIS 画布。

> ✅ **已完成**（2026-05-20 初版，2026-05-21 最终修正）：
> - 删除左侧 `GISLayerControlSidebar` 中的 `VisualizationSettingsWidget`，避免出现两个类别颜色配置
> - 类别颜色配置保留在右侧 `InferencePanel.groupBox_inferenceResult`，推理完成后自动显示
> - `inference_panel.visualization_settings.palette_changed/alpha_changed/apply_requested` 已连接到 GIS 画布
> - 仅隐藏/移除右侧预览图控件 `visualization_widget`（不添加到布局），保留推理结果文字与类别颜色配置
> - `GISCanvasWidget` 新增 `_prediction_palette` 缓存，确保颜色配置可靠应用

---

## Phase 5 — 背景类透明修复 + 导出格式优化（✅ 已完成）

**目标**：修复 class0 背景颜色无法响应的问题；将导出格式改为语义分割常用格式。

> ✅ **已完成**（2026-05-21）：
> - `apply_label_colormap` 中 class_id=0 不再硬编码 alpha=0，当用户自定义了非黑色背景时显示颜色
> - 导出格式从 PNG/NumPy/JSON 改为 GeoTIFF/PNG/NumPy，GeoTIFF 为默认选中
> - GeoTIFF 导出时自动从原始影像复制地理坐标信息（CRS + Transform）
> - rasterio 不可用时优雅降级为 PIL 保存 TIFF（无地理信息）
> - 删除 `InferencePanel._connect_signals()` 中内部预览渲染信号连接，避免点击颜色配置后弹出独立预览窗口
> - 颜色配置信号统一由 MainWindow 外部连接到 GIS 画布，class0 背景颜色可正常响应
> - 删除 `_handle_inference_success()` 中两处 `_render_inference_result()` 调用，消除推理完成后自动弹出预览窗口的行为
