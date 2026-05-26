# Tab2「任务配置与训练」改进方案

> **基于**: `docs/TAB2_TRAINING_ANALYSIS.md` v2.0 中标记为 ✔ 需要修改的条目
> **确认修改项**: BUG-01, BUG-02, BUG-05, BUG-06, UI-01, UI-02, UI-03, UI-06, UI-07, UI-08

---

## 确认修改条目汇总

| 编号 | 类型 | 简述 | 特殊说明 |
|------|------|------|---------|
| BUG-01 | Bug | `num_classes` 未注入 | 仅修 num_classes，metainfo 暂不做 |
| BUG-02 | Bug | `img_suffix`/`seg_map_suffix` 未覆写 | 全量修复 |
| BUG-05 | Bug | `val_interval` 被强制覆盖 | 全量修复 |
| BUG-06 | Bug | `save_best` 未注入 | 全量修复 |
| UI-01 | UI | 缺少类别数量确认控件 | 仅做 num_classes 确认，class_names/palette 暂不添加 |
| UI-02 | UI | 缺少训练前配置确认弹窗 | 全量实现 |
| UI-03 | UI | 导出按钮悬空 | 全量实现 |
| UI-06 | UI | 算法/Backbone 覆盖不足 | 全量实现 |
| UI-07 | UI | 缺少后缀手动输入控件 | 全量实现 |
| UI-08 | UI | 预训练权重管理不完善 | 含注入断链修复 + 下载功能 |

---

## Phase 划分

```
Phase 1：训练核心正确性（数据格式与类别数量）
  ├── BUG-01（num_classes 链路打通）
  ├── BUG-02（后缀自动探测 + 覆写）
  ├── UI-01（num_classes 确认控件）
  └── UI-07（后缀下拉选择控件）

Phase 2：训练参数有效性（让 UI 设置真正生效）
  ├── BUG-05（val_interval 优先读用户设置）
  ├── BUG-06（save_best 注入 checkpoint hook）
  └── UI-08 第一步（自定义权重路径注入断链修复）

Phase 3：训练前验证与操作体验
  ├── UI-02（训练前配置确认弹窗）
  └── UI-03（导出按钮连接实现）

Phase 4：模型算法库扩充
  └── UI-06（METHOD_BACKBONE_MAP + CONFIG_MAP 扩充）

Phase 5：预训练权重管理完善
  └── UI-08 第二步（本地缓存扫描 + 下载功能）
```

### 依赖关系

```
Phase 1 → Phase 2（UI-02 弹窗需显示 num_classes，依赖 Phase 1）
Phase 1 → Phase 3（弹窗需显示后缀信息，依赖 UI-07 的 get_params()）
Phase 2 → Phase 3（弹窗需显示 val_interval/save_best 实际值）
Phase 4 独立（可并行）
Phase 5 依赖 Phase 2（UI-08 第一步的断链修复）
```

**建议执行顺序**: Phase 1 → Phase 2 → Phase 3 → Phase 4/5（并行）

---

## Phase 1 — 训练核心正确性

### 目标

消除训练必定崩溃的根本原因。本阶段完成前，任何用户的第一次训练都会失败。

---

### 1.1 num_classes 数据链路打通（BUG-01 + UI-01）

**改动三环节**：

#### 环节① config_advisor.py

`ConfigAdvisor.from_database()` 中补充 `class_names` 赋值：

```python
# 从 pixel_distribution 的 key 数量推断类别数
insights.class_names = [f"class_{i}" for i in range(len(insights.pixel_distribution))]
```

`recommend_rs_params()` 新增返回字段：

```python
return {
    'in_channels': ins.num_channels,
    'num_classes': ins.num_classes,       # ← 新增
    'crop_size': self._recommend_crop_size(),
    'class_weight': class_weight,
    'loss_config': self.recommend_loss_config(),
    'augmentation': self.recommend_augmentation(),
}
```

#### 环节② UI-01 控件（Tab2 任务配置区）

在 `HyperparamTabsWidget` 的「常规参数」Tab 中，`spin_in_channels` 之前新增：

```
spin_num_classes: QSpinBox (range: 2~256, default: 2)
- Tooltip: "数据集类别总数（含背景类）"
- 自动从 advisor_params['num_classes'] 填入
- 用户可手动修改
- get_params() 新增返回 'num_classes' 字段
```

联动逻辑：
- `_on_generate_recommend_config()` 中将 `rs_params['num_classes']` 推送给该控件
- Tab1 分析完成后，通过信号自动更新

#### 环节③ mmseg_trainer.py

`generate_config()` 中新增注入块（在数据集路径处理之后、预训练权重之前）：

```python
# ====== num_classes 注入 ======
num_classes = ui_params.get('num_classes')
if num_classes:
    num_classes = int(num_classes)
    if hasattr(cfg.model, 'decode_head'):
        cfg.model.decode_head.num_classes = num_classes
    if hasattr(cfg.model, 'auxiliary_head'):
        cfg.model.auxiliary_head.num_classes = num_classes
```

---

### 1.2 影像/掩膜后缀（BUG-02 + UI-07）

#### 后端：mmseg_trainer.py

新增辅助函数：

```python
def _detect_suffix(dir_path: str, default: str = '.jpg') -> str:
    """扫描目录下第一个文件的扩展名，无文件时返回 default"""
    if not os.path.isdir(dir_path):
        return default
    for f in os.listdir(dir_path):
        _, ext = os.path.splitext(f)
        if ext:
            return ext.lower()
    return default
```

在 `process_segmentation_split()` 的强转块中：

```python
obj['type'] = 'PascalVOCDataset'
obj['reduce_zero_label'] = False
obj['img_suffix'] = ui_params.get('img_suffix') or _detect_suffix(
    os.path.join(data_root, 'JPEGImages'))
obj['seg_map_suffix'] = ui_params.get('seg_map_suffix') or _detect_suffix(
    os.path.join(data_root, 'SegmentationClass'), default='.png')
```

#### 前端：hyperparam_tabs_widget.py

在「常规参数」Tab 末尾新增两个可编辑下拉框：

```
combo_img_suffix:     QComboBox (editable=True)
  items: ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
  default: '.jpg'（由 Tab1 加载数据集时通过信号更新为探测值）

combo_seg_map_suffix: QComboBox (editable=True)
  items: ['.png', '.tif', '.tiff']
  default: '.png'
```

`get_params()` 新增返回：
```python
'img_suffix': self.combo_img_suffix.currentText(),
'seg_map_suffix': self.combo_seg_map_suffix.currentText(),
```

联动：Tab1 加载数据集完成后，通过信号将探测到的后缀推送给这两个下拉控件。

---

## Phase 2 — 训练参数有效性

### 目标

让用户在 UI 中设置的超参数完整写入训练配置文件。

---

### 2.1 val_interval 优先读用户设置（BUG-05）

**文件**: `mmseg_trainer.py`

**改动**: 1 行

```python
# 改前
val_interval = max(50, int(max_iters) // 10)

# 改后
val_interval = int(ui_params.get('val_interval') or 0) or max(50, int(max_iters) // 10)
```

---

### 2.2 save_best 注入（BUG-06）

**文件**: `mmseg_trainer.py`

在 checkpoint hook 配置块后追加：

```python
save_best = ui_params.get('save_best', True)
if save_best:
    if hasattr(cfg, 'default_hooks') and hasattr(cfg.default_hooks, 'checkpoint'):
        cfg.default_hooks.checkpoint.save_best = 'mIoU'
        cfg.default_hooks.checkpoint.rule = 'greater'
```

---

### 2.3 自定义权重路径注入断链修复（UI-08 第一步）

**文件**: `scripts/data_source_tree_example.py`

在 `_on_start_training()` 组装 `ui_params` 时（Step 2 末尾）补充：

```python
# ====== 预训练权重路径映射 ======
if weight_params.get('use_custom_weight') and weight_params.get('custom_weight_path'):
    ui_params['pretrained'] = weight_params['custom_weight_path']
elif weight_params.get('use_pretrained'):
    ui_params['pretrained'] = weight_params.get('pretrained_model', '')
```

这确保 `WeightSelectionWidget` 中用户选择的自有权重路径能正确传递到 `MMSegTrainer.generate_config()` 中被消费。

---

## Phase 3 — 训练前验证与操作体验

### 目标

在用户点击「运行」之后、训练真正启动之前，提供关键配置的视觉确认；同时补全已存在但无效的导出功能。

---

### 3.1 训练前配置汇总确认弹窗（UI-02）

**文件**: `scripts/data_source_tree_example.py`

**新增方法**: `_show_pretrain_confirm_dialog(ui_params: dict, config_path: str) -> bool`

**插入位置**: `_on_start_training()` 的 Step 4（生成配置文件）与 Step 5（启动 TrainingThread）之间。

**弹窗内容**（从 `ui_params` 读取）：

| 字段 | 来源 |
|------|------|
| 算法 / Backbone | `model_params['method']` / `model_params['backbone']` |
| 类别数量 | `ui_params['num_classes']` |
| 数据根目录 | `ui_params['data_root']` |
| 影像后缀 / 掩膜后缀 | `ui_params['img_suffix']` / `ui_params['seg_map_suffix']` |
| Batch Size | `ui_params['batch_size']` |
| Max Iters | `ui_params['max_iters']` |
| 验证间隔 | `ui_params['val_interval']` |
| 学习率 / 优化器 | `ui_params['lr']` / `ui_params['optimizer']` |
| 保存最佳模型 | `ui_params['save_best']` |
| 配置文件路径 | `config_path` |

**按钮**：
- 「📄 查看完整配置」→ `os.startfile(config_path)`（Windows）/ `subprocess.Popen(['xdg-open', config_path])`
- 「取消」→ 返回 `False`，不启动训练
- 「▶ 开始训练」→ 返回 `True`，继续 Step 5

**实现要点**：
- 使用 `QDialog` + `QFormLayout` 构建
- 返回 `False` 时，`_on_start_training()` 直接 `return`

---

### 3.2 导出配置按钮实现（UI-03）

**文件**: `scripts/data_source_tree_example.py`

#### 信号连接

在 `_connect_signals()` 中添加：

```python
self.ui.pushButton_export.clicked.connect(self._on_export_config)
```

#### 新增方法

```python
def _on_export_config(self):
    """导出当前训练配置文件到用户指定路径"""
    config_path = getattr(self, '_last_config_path', None)
    if not config_path or not os.path.isfile(config_path):
        QMessageBox.information(self, "导出配置",
            "尚未生成训练配置文件。\n请先点击「运行」生成配置，或在确认弹窗中查看。")
        return

    save_path, _ = QFileDialog.getSaveFileName(
        self, "导出训练配置", config_path,
        "Python 配置文件 (*.py);;所有文件 (*)")
    if save_path:
        import shutil
        shutil.copy2(config_path, save_path)
        self.statusBar().showMessage(f"✅ 配置已导出到: {save_path}")
```

#### 缓存时机

在 `_on_start_training()` 生成配置后立即缓存：

```python
config_path = trainer.generate_config(ui_params, advisor_params, config_save_path)
self._last_config_path = config_path  # ← 新增
```

---

## Phase 4 — 模型算法库扩充

### 目标

让用户能选择遥感语义分割领域主流方案，覆盖「轻量快速 / 标准精度 / 高精度 SOTA」三档。

---

### 4.1 扩充方案

| 档次 | 定位 | 新增算法/Backbone |
|------|------|-----------------|
| 🟢 轻量快速 | 快速实验、边缘部署 | FCN + ResNet-18、DeepLabV3+ + MobileNetV3 |
| 🔵 标准精度 | 项目首选 | UNet++ + ResNet-50/101、HRNet+OCR + HRNet-W32/W48、UperNet + ConvNeXt-Tiny |
| 🟣 高精度 SOTA | 算力充足 | Mask2Former + Swin-Large、SegFormer + MiT-B3/B4（补充）、UperNet + BEiT-Large |

---

### 4.2 改动位置

#### `model_selection_widget.py`

**METHOD_BACKBONE_MAP 新增**：

```python
'UNet++': ['ResNet-50', 'ResNet-101'],
'Mask2Former': ['Swin-Tiny', 'Swin-Base', 'Swin-Large', 'ResNet-50'],
'HRNet+OCR': ['HRNet-W32', 'HRNet-W48'],
# 现有算法补充 Backbone：
'DeepLabV3+': [..., 'MobileNetV3'],   # 追加
'FCN': [..., 'ResNet-18'],            # 追加
'SegFormer': [..., 'MiT-B3', 'MiT-B4'],  # 追加
```

**BACKBONE_CHOICES 新增**：

```python
'ResNet-18': 'resnet18',
'HRNet-W32': 'hrnet_w32',
'MobileNetV3': 'mobilenet_v3_large',
'ConvNeXt-Tiny': 'convnext_tiny',
'BEiT-Large': 'beit_large',
'MiT-B3': 'mit_b3',
'MiT-B4': 'mit_b4',
```

#### `data_source_tree_example.py` → `_find_base_config()` CONFIG_MAP

```python
# 新增映射
('UNet++', 'resnet50'):       ('unet', 'unet-s5-d16_fcn_4xb4*512x512*.py'),
('UNet++', 'resnet101'):      ('unet', 'unet-s5-d16_fcn_4xb4*512x512*.py'),
('Mask2Former', 'swin_tiny'): ('mask2former', 'mask2former_swin-t*512x512*.py'),
('Mask2Former', 'swin_base'): ('mask2former', 'mask2former_swin-b*512x512*.py'),
('Mask2Former', 'swin_large'):('mask2former', 'mask2former_swin-l*512x512*.py'),
('Mask2Former', 'resnet50'):  ('mask2former', 'mask2former_r50*512x512*.py'),
('HRNet+OCR', 'hrnet_w32'):   ('ocrnet', 'ocrnet_hr32*512x512*.py'),
('HRNet+OCR', 'hrnet_w48'):   ('ocrnet', 'ocrnet_hr48*512x512*.py'),
('DeepLabV3+', 'mobilenet_v3_large'): ('mobilenet_v3', 'deeplabv3plus_m-v3*512x512*.py'),
('FCN', 'resnet18'):          ('fcn', 'fcn_r18*d8*512x512*.py'),
('SegFormer', 'mit_b3'):      ('segformer', 'segformer_mit-b3*512x512*.py'),
('SegFormer', 'mit_b4'):      ('segformer', 'segformer_mit-b4*512x512*.py'),
```

> 注：glob 模式需根据 MMSeg 实际 configs/ 目录结构微调。

---

## Phase 5 — 预训练权重管理完善

### 目标

解决小白用户面对预训练权重时「不知道去哪里找、不知道怎么放」的问题。

---

### 5.1 本地缓存自动扫描

**文件**: `weight_selection_widget.py`

**触发时机**: 用户切换 Backbone 时（`update_backbone()` 被调用时）

**逻辑**：

```python
def _scan_local_pretrain(self, backbone_key: str):
    """扫描 pretrain/ 目录，自动匹配已下载的权重文件"""
    pretrain_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pretrain')
    if not os.path.isdir(pretrain_dir):
        return
    for f in os.listdir(pretrain_dir):
        if f.endswith('.pth') and backbone_key in f:
            self.line_custom_weight.setText(os.path.join(pretrain_dir, f))
            self.check_use_custom_weight.setChecked(True)
            break
```

---

### 5.2 公共预训练权重下载功能

**文件**: `weight_selection_widget.py`（新增下载按钮 + 下载线程）

#### WEIGHT_URL_MAP（维护在 Widget 或独立常量文件中）

```python
WEIGHT_URL_MAP = {
    ('MiT-B0', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/segformer/mit_b0_20220624-7e0fe6dd.pth',
    ('ResNet-50', 'ImageNet-1K'): 'https://download.openmmlab.com/pretrain/third_party/resnet50_v1c-2cccc1ad.pth',
    ('Swin-Tiny', 'ImageNet-1K'): 'https://download.openmmlab.com/mmsegmentation/v0.5/pretrain/swin/swin_tiny_patch4_window7_224_20220317-1cdeb081.pth',
    # ... 按需扩充
}
```

#### 下载流程

```
1. 用户点击「⬇ 下载」按钮
2. 查表获取 URL（key = (backbone_name, pretrained_dataset)）
3. 弹出确认对话框：文件名、保存路径（pretrain/xxx.pth）
4. 启动 QThread 下载线程：
   - requests.get(url, stream=True)
   - 每 chunk 更新 QProgressBar
   - 支持取消（通过 stop_event）
5. 下载完成：
   - 自动切换到「自有权重」Tab
   - 填入下载路径到 line_custom_weight
   - 勾选 check_use_custom_weight
6. 下载失败：
   - 显示错误提示
   - 提供手动下载链接（可复制）
```

#### UI 改动

在「公共预训练」Tab 的 `pretrained_row` 后追加下载按钮：

```python
self.btn_download = QPushButton("⬇ 下载")
self.btn_download.setToolTip("下载选中的预训练权重到本地 pretrain/ 目录")
self.btn_download.clicked.connect(self._on_download_weight)
pretrained_row.addWidget(self.btn_download)
```

---

## 汇总与建议执行顺序

| Phase | 涉及条目 | 核心改动文件 | 预估工作量 |
|-------|---------|------------|-----------|
| 1 | BUG-01, BUG-02, UI-01, UI-07 | `config_advisor.py`, `mmseg_trainer.py`, `hyperparam_tabs_widget.py` | 中 |
| 2 | BUG-05, BUG-06, UI-08(断链) | `mmseg_trainer.py`, `data_source_tree_example.py` | 低 |
| 3 | UI-02, UI-03 | `data_source_tree_example.py` | 中 |
| 4 | UI-06 | `model_selection_widget.py`, `data_source_tree_example.py` | 低 |
| 5 | UI-08(下载) | `weight_selection_widget.py` | 中 |

---

### 风险与注意事项

1. **Phase 1 的 `_detect_suffix()` 需健壮处理空目录**：目录不存在或无文件时返回合理默认值
2. **Phase 4 扩充算法时**，glob 模式需根据用户安装的 MMSeg 版本实际 configs/ 目录验证
3. **Phase 5 下载功能**需处理网络超时、代理、大文件断点续传等边界情况
4. **Phase 3 确认弹窗**中「查看完整配置」在 Linux 上需用 `xdg-open` 替代 `os.startfile`
5. **所有 Phase 完成后**，建议进行一次端到端集成测试：加载数据集 → 生成推荐 → 确认配置 → 启动训练 → 验证配置文件内容正确

---

### 验收标准

| Phase | 验收条件 |
|-------|---------|
| 1 | 生成的 `train_config.py` 中 `decode_head.num_classes` 与用户数据集一致；`img_suffix` 与实际文件格式一致 |
| 2 | UI 中设置的 `val_interval`、`save_best` 在生成配置中可见；自定义权重路径出现在 `cfg.model.init_cfg` 中 |
| 3 | 点击运行后弹出确认弹窗，取消后不启动训练；导出按钮可将配置另存为 |
| 4 | 新增算法在下拉框中可选，且 `_find_base_config()` 能找到对应配置文件 |
| 5 | 点击下载按钮后权重文件出现在 `pretrain/` 目录，路径自动填入 Widget |

---

---

## 实施记录

### 完成状态

| Phase | 条目 | 状态 | 改动文件 |
|-------|------|------|---------|
| 1 | BUG-01 num_classes 链路 | ✅ 完成 | `config_advisor.py`, `mmseg_trainer.py`, `hyperparam_tabs_widget.py`, `data_source_tree_example.py` |
| 1 | BUG-02 后缀自动探测 | ✅ 完成 | `mmseg_trainer.py` |
| 1 | UI-01 num_classes 控件 | ✅ 完成 | `hyperparam_tabs_widget.py`（新增 `spin_num_classes`、`set_num_classes()`） |
| 1 | UI-07 后缀下拉控件 | ✅ 完成 | `hyperparam_tabs_widget.py`（新增 `combo_img_suffix`、`combo_seg_map_suffix`、`set_suffixes()`） |
| 2 | BUG-05 val_interval | ✅ 完成 | `mmseg_trainer.py`（优先读 `ui_params['val_interval']`） |
| 2 | BUG-06 save_best | ✅ 完成 | `mmseg_trainer.py`（注入 `default_hooks.checkpoint.save_best`） |
| 2 | UI-08 权重路径断链 | ✅ 完成 | `data_source_tree_example.py`（`custom_weight_path` → `ui_params['pretrained']`） |
| 3 | UI-02 训练前确认弹窗 | ✅ 完成 | `data_source_tree_example.py`（新增 `_show_pretrain_confirm_dialog()`） |
| 3 | UI-03 导出按钮 | ✅ 完成 | `data_source_tree_example.py`（连接信号 + 新增 `_on_export_config()`） |
| 4 | UI-06 算法库扩充 | ✅ 完成 | `model_selection_widget.py`（扩充 `METHOD_BACKBONE_MAP`、`BACKBONE_CHOICES`）、`data_source_tree_example.py`（扩充 `CONFIG_MAP`） |
| 5 | UI-08 下载功能 | ✅ 完成 | `weight_selection_widget.py`（新增 `WeightDownloadWorker`、下载按钮、进度条、本地缓存扫描） |

### 测试结果

```
python -m py_compile core\config_advisor.py \
    core\framework_adapters\mmseg_trainer.py \
    ui\widgets\hyperparam_tabs_widget.py \
    ui\widgets\model_selection_widget.py \
    ui\widgets\weight_selection_widget.py \
    scripts\data_source_tree_example.py
→ ALL OK（语法检查通过，无 IDE 诊断错误）
```

### 主要改动点汇总

**`core/config_advisor.py`**
- `from_database()` 中从 `pixel_distribution` key 数量推断 `class_names`
- `recommend_rs_params()` 新增返回 `num_classes` 字段

**`core/framework_adapters/mmseg_trainer.py`**
- 新增模块级辅助函数 `_detect_suffix(dir_path, default)`
- `process_segmentation_split()` 强转 `PascalVOCDataset` 后写入 `img_suffix`、`seg_map_suffix`
- `generate_config()` 新增 `num_classes` 注入块（`decode_head` + `auxiliary_head`）
- `val_interval` 改为优先读 `ui_params['val_interval']`
- `default_hooks.checkpoint` 新增 `save_best='mIoU'` 注入

**`ui/widgets/hyperparam_tabs_widget.py`**
- 「常规参数」Tab 新增 `spin_num_classes`（类别数量）
- 「常规参数」Tab 新增 `combo_img_suffix`、`combo_seg_map_suffix`（文件后缀）
- `get_params()` 新增返回 `num_classes`、`img_suffix`、`seg_map_suffix`
- 新增公共 API：`set_num_classes()`、`set_suffixes()`

**`ui/widgets/model_selection_widget.py`**
- `METHOD_BACKBONE_MAP` 新增：`UNet++`、`Mask2Former`、`HRNet+OCR`；`DeepLabV3+` 补充 `MobileNetV3`；`FCN` 补充 `ResNet-18`；`UperNet` 补充 `ConvNeXt-Tiny`；`SegFormer` 补充 `MiT-B3/B4`
- `BACKBONE_CHOICES` 新增：`resnet18`、`mobilenet_v3_large`、`hrnet_w32`、`convnext_tiny`、`mit_b3`、`mit_b4`

**`ui/widgets/weight_selection_widget.py`**
- 新增模块级常量 `WEIGHT_URL_MAP`
- 新增 `WeightDownloadWorker(QThread)`：流式下载、进度信号、取消支持
- 公共预训练 Tab 新增「⬇ 下载」按钮和 `QProgressBar`
- `update_backbone()` 调用 `_scan_local_pretrain()` 自动检测本地缓存
- 新增 `_scan_local_pretrain()`、`_on_download_weight()`、`_on_download_finished()`、`_on_download_failed()`

**`scripts/data_source_tree_example.py`**
- `_connect_signals()` 连接 `pushButton_export` → `_on_export_config`
- `_on_generate_recommend_config()` 将 `rs_params['num_classes']` 推送给 `widget_hyperparamTabs.set_num_classes()`
- `_on_start_training()` 新增权重路径映射（`custom_weight_path` → `ui_params['pretrained']`）
- `_on_start_training()` 生成配置后缓存 `_last_config_path`，并在启动线程前调用 `_show_pretrain_confirm_dialog()`
- 新增 `_show_pretrain_confirm_dialog(ui_params, model_params, config_path) -> bool`
- 新增 `_on_export_config()`
- `_find_base_config()` 的 `CONFIG_MAP` 新增 14 个算法/Backbone 组合映射

---

*文档版本: v2.0 | 实施完成时间: 2025年*

---

## 第二轮新增改进方案（基于「添加修改」标记）

> **说明**：以下内容来自 `docs/TAB2_TRAINING_ANALYSIS.md` 中用户新增标注为「添加修改」的条目，
> 在第一轮已完成修改的基础上，补充原先暂缓或新增的工作。
> 已完成的 Phase 1～5 代码**不受影响**，本轮新增任务编号从 **Phase 6** 开始。

### 新增条目汇总

| 来源条目 | 原状态 | 新增说明 |
|---------|--------|---------|
| BUG-01 | 第一轮仅完成 `num_classes` 注入 | **补完**：将 `class_names` + `palette` 写入各 dataloader 的 `dataset.metainfo` |
| BUG-04 | 第一轮标为「暂不修改」 | **新增**：子进程启动时注入目标 conda 环境 PATH / DLL 路径 |
| UI-01 | 第一轮仅新增 `spin_num_classes` 控件 | **补完**：新增类别名称可编辑列表 + 颜色选择器，实现完整的「类别配置」区域 |

### 依赖关系

```
Phase 6（BUG-04 PATH注入）独立，无前置依赖，可最先实施
Phase 7（BUG-01 metainfo 注入）依赖 Phase 8 的 UI-01 提供 class_names 输入源
Phase 8（UI-01 完整类别配置控件）是 Phase 7 的数据来源，应先于 Phase 7 实施
建议执行顺序：Phase 6 → Phase 8 → Phase 7
```

---

## Phase 6 — 子进程 PATH / DLL 路径注入（BUG-04）

### 目标

修复 Windows 下跨 conda 环境训练时，因 `Library\bin\` 未加入 PATH 导致 CUDA DLL
找不到（`OSError: [WinError 127]`）的致命问题。本阶段独立于其他 Phase，可优先实施。

### 背景

第一轮改进中，BUG-04 被标为「暂不修改」，现在补做。
`mmseg_trainer.py` 的 `start_training()` 构建子进程 `env` 时只追加了 `PYTHONPATH`，
没有将目标 Python 解释器所在 conda 环境的以下目录注入 `PATH`：
- `{env_root}/`（python.exe 所在目录）
- `{env_root}/Scripts/`（Windows 脚本目录）
- `{env_root}/Library/bin/`（CUDA、HDF5 等动态库）
- `{env_root}/Library/usr/bin/`
- `{env_root}/bin/`（Linux/macOS）

### 改动位置

**文件**: `core/framework_adapters/mmseg_trainer.py`
**方法**: `start_training()`

### 实现方案

在已有的 `PYTHONPATH` 追加逻辑之后，增加 PATH 注入块：

```python
# ====== 注入目标 conda 环境的 PATH（解决 Windows CUDA DLL 丢失）======
if python_path and os.path.isfile(python_path):
    env_root = os.path.dirname(python_path)
    extra_paths = [
        env_root,
        os.path.join(env_root, 'Scripts'),
        os.path.join(env_root, 'Library', 'bin'),
        os.path.join(env_root, 'Library', 'usr', 'bin'),
        os.path.join(env_root, 'bin'),
    ]
    existing_path = env.get('PATH', '')
    env['PATH'] = os.pathsep.join(
        [p for p in extra_paths if os.path.isdir(p)] + [existing_path]
    )
```

### 注意事项

1. `extra_paths` 中的路径必须使用 `if os.path.isdir(p)` 过滤，避免向 PATH 注入不存在的目录
2. 注入路径需**前置**（放在 `existing_path` 之前），否则系统默认 Python 可能仍被优先找到
3. Linux/macOS 上 `bin/` 路径有效，`Scripts/`、`Library/bin/` 目录不存在会被过滤，不影响跨平台兼容性
4. `python_path` 可能为 `None`（未选择解释器），加 `if python_path` 判断保护

### 验收标准

- 在 Windows 多 conda 环境下（GUI 在环境 A，训练在环境 B），子进程能正常 `import torch` 而不报 `WinError 127`
- Linux/macOS 下行为不变（`Scripts/`、`Library/bin/` 被过滤掉，`bin/` 正常加入）

---

## Phase 7 — BUG-01 补完：`metainfo`（class_names + palette）注入

### 目标

补完第一轮中对 BUG-01 的修复——在 `num_classes` 已注入的基础上，进一步将
`class_names`（类别名称表）和 `palette`（颜色表）写入各 dataloader 的
`dataset.metainfo`，使 MMSeg 在验证和推理时能正确显示类别标签和颜色。

**依赖 Phase 8**：`class_names` 和 `palette` 的数据来源是 Phase 8 新增的
UI-01 完整控件（`ClassConfigWidget`），Phase 7 需在 Phase 8 完成后实施。

### 数据流

```
Phase 8 新增控件（ClassConfigWidget）
    └── get_class_config() → { 'class_names': [...], 'palette': [[r,g,b], ...] }
            │
            ▼ 由 MainWindow._on_start_training() 写入 ui_params
    ui_params['class_names'] = [...]
    ui_params['palette']     = [...]
            │
            ▼ 传入 MMSegTrainer.generate_config(ui_params, ...)
    Phase 7 在此处注入 metainfo
```

### 改动位置

**文件**: `core/framework_adapters/mmseg_trainer.py`
**方法**: `generate_config()`，在已有的 `num_classes 注入` 块之后追加

### 实现方案

```python
# ====== metainfo 注入（class_names + palette）======
class_names = ui_params.get('class_names')  # list[str]，来自 Phase 8 控件
palette     = ui_params.get('palette')       # list[list[int]]，来自 Phase 8 控件

if class_names and hasattr(cfg, 'model'):
    meta = dict(classes=tuple(class_names))
    if palette and len(palette) == len(class_names):
        meta['palette'] = [tuple(c) for c in palette]

    for dl_key in ('train_dataloader', 'val_dataloader', 'test_dataloader'):
        if hasattr(cfg, dl_key):
            dl = getattr(cfg, dl_key)
            if hasattr(dl, 'dataset'):
                dl.dataset.metainfo = meta
```

同时在 `data_source_tree_example.py` 的 `_on_start_training()` 中，
从 Phase 8 的控件读取数据并写入 `ui_params`：

```python
# 在组装 ui_params 阶段追加（Phase 7 改动）
if hasattr(self.ui, 'widget_classConfig'):
    class_cfg = self.ui.widget_classConfig.get_class_config()
    ui_params['class_names'] = class_cfg.get('class_names', [])
    ui_params['palette']     = class_cfg.get('palette', [])
```

### 注意事项

1. `class_names` 为空列表时不注入（保持 base_config 原有的 `metainfo`，避免覆盖为空）
2. `palette` 长度必须与 `class_names` 一致，否则仅注入 `classes` 不注入 `palette`
3. `PascalVOCDataset` 的 `metainfo` 覆写格式为 `dict(classes=tuple(...), palette=[...])`，
   与 0.x 的 `CLASSES` / `PALETTE` 类属性不同，需使用 MMSeg 1.x 格式
4. 若 Tab1 没有运行分析，`class_names` 可能来自用户手动输入（Phase 8 控件允许手动编辑）

### 验收标准

- 生成的 `train_config.py` 中，三个 dataloader 的 `dataset.metainfo` 包含正确的 `classes` 元组
- 有 `palette` 时，`metainfo` 中同时包含 `palette` 字段
- `num_classes` 与 `len(class_names)` 一致（Phase 8 控件应联动 `spin_num_classes`）

---

## Phase 8 — UI-01 补完：完整「类别配置」控件（class_names + palette）

### 目标

补完第一轮中 UI-01 的实现——在已有 `spin_num_classes`（类别数量 SpinBox）的基础上，
新增一个完整的「类别配置」分组框，包含：

1. **类别名称可编辑列表**：每行对应一个类别，可修改名称、添加/删除行
2. **类别颜色选择器**：每行右侧附一个颜色块按钮，点击弹出颜色选择对话框
3. **自动同步**：`spin_num_classes` 数值变化时，列表行数自动增减

**注意**：`spin_num_classes` 已在 Phase 1 实现，本 Phase 在其基础上扩展，
不修改或废弃 `spin_num_classes`，只在其下方追加新控件区域。

### 改动位置

**新建文件（推荐）**: `ui/widgets/class_config_widget.py`
**或嵌入位置**: `ui/widgets/hyperparam_tabs_widget.py`（在「常规参数」Tab 中扩展）

推荐新建独立 Widget，理由：
- 类别配置逻辑较复杂（动态行、颜色选择、联动），独立文件更易维护
- 将来 Tab3 推理面板也可能复用同一控件（统一类别颜色配置）

### 新建 `ClassConfigWidget` 设计

```
ClassConfigWidget (QWidget)
│
├── 说明标签: "定义数据集的类别名称和可视化颜色"
│
├── QTableWidget (class_table)
│   ├── 列 0: 类别 ID（只读，0, 1, 2...）
│   ├── 列 1: 类别名称（可编辑 QLineEdit）
│   └── 列 2: 颜色（QPushButton，背景色为当前颜色，点击弹 QColorDialog）
│
├── 操作按钮行
│   ├── [+ 添加类别] → 末尾追加一行
│   └── [- 删除选中] → 删除当前选中行（保留至少 2 行）
│
└── 联动：外部调用 set_num_classes(n) 时自动增/删行至 n 行
```

### Public API

```python
class ClassConfigWidget(QWidget):

    config_changed = Signal()

    def set_num_classes(self, n: int):
        """由 spin_num_classes 联动调用，自动增减行数至 n 行。
        新增行自动填入默认名称 class_{id} 和默认颜色。"""

    def get_class_config(self) -> dict:
        """返回 {'class_names': [...], 'palette': [[r,g,b], ...]}"""

    def load_from_advisor(self, class_names: list, palette: list = None):
        """由推荐系统或 Tab1 联动调用，批量填入类别名和颜色。"""
```

### 与现有代码的集成

**`main_frame_ui.py`**：在 `groupBox_modelSelection`（模型选择组）之后，
`groupBox_advisorConfig`（推荐配置组）之前，插入新的 `groupBox_classConfig` 分组框：

```python
self.groupBox_classConfig = QGroupBox("类别配置 (Class Configuration)")
self.widget_classConfig = ClassConfigWidget(self.groupBox_classConfig)
# 插入到 scrollAreaWidget_taskConfig 的布局中
```

**`scripts/data_source_tree_example.py`**：

1. `_connect_signals()` 中：
   - `spin_num_classes.valueChanged` → `widget_classConfig.set_num_classes()`（联动）
   - `widget_classConfig.config_changed` → `_on_config_params_changed()`

2. `_on_generate_recommend_config()` 中：
   - 推荐生成后调用 `widget_classConfig.load_from_advisor(class_names)`

3. `_on_start_training()` 中（见 Phase 7）：
   - 读取 `widget_classConfig.get_class_config()` 并写入 `ui_params`

### 默认颜色方案

新增行时，自动按以下顺序分配默认颜色（循环），参考 VOC 经典调色板：

```python
DEFAULT_PALETTE = [
    (0, 0, 0),        # class_0  黑（背景）
    (128, 0, 0),      # class_1  深红
    (0, 128, 0),      # class_2  深绿
    (128, 128, 0),    # class_3  橄榄
    (0, 0, 128),      # class_4  深蓝
    (128, 0, 128),    # class_5  紫
    (0, 128, 128),    # class_6  深青
    (128, 128, 128),  # class_7  灰
    (64, 0, 0),       # class_8  暗红
    (192, 0, 0),      # class_9  亮红
]
```

### 注意事项

1. `QTableWidget` 的颜色列使用 `QPushButton` + `setStyleSheet("background-color: rgb(r,g,b)")` 实现颜色预览，点击触发 `QColorDialog.getColor()`
2. 删除行时应同步更新第 0 列（类别 ID）的显示值（重新编号）
3. `spin_num_classes` 联动：当用户在 `ClassConfigWidget` 中手动添加/删除行时，应反向更新 `spin_num_classes` 的值，保持一致
4. 控件初始化时默认显示 2 行（背景 class_0 + 目标 class_1），与 `spin_num_classes` 的默认值 2 对齐
5. `load_from_advisor()` 调用时，若当前已有用户手动编辑的内容，应弹出确认对话框询问是否覆盖

### 验收标准

- 「类别配置」分组框在 Tab2 任务配置区域中可见
- `spin_num_classes` 从 2 改为 3 时，表格自动追加第 3 行（`class_2`）
- 点击颜色按钮，颜色选择对话框弹出，选色后按钮背景和预览更新
- `get_class_config()` 返回的 `class_names` 和 `palette` 长度与行数一致
- `load_from_advisor(['background', 'water', 'road'])` 后，表格填入对应名称

---

## 第二轮新增条目总表

| Phase | 条目 | 优先级 | 状态 | 核心改动文件 |
|-------|------|--------|------|------------|
| 6 | BUG-04 子进程 PATH 注入 | 🔴 独立修复，优先做 | ✅ 完成 | `mmseg_trainer.py` |
| 8 | UI-01 完整类别配置控件 | 🟠 Phase 7 的前置依赖 | ✅ 完成 | 新建 `class_config_widget.py`、`main_frame_ui.py` |
| 7 | BUG-01 metainfo 注入 | 🟠 依赖 Phase 8 | ✅ 完成 | `mmseg_trainer.py`、`data_source_tree_example.py` |

**建议执行顺序**：Phase 6（独立，最短）→ Phase 8（新建控件）→ Phase 7（metainfo 注入）

---

### 第二轮实施记录

**Phase 6 — `core/framework_adapters/mmseg_trainer.py`**
- `start_training()` 中在 `PYTHONPATH` 追加之后，新增 PATH 注入块
- 将目标 conda 环境的 `Scripts/`、`Library/bin/`、`Library/usr/bin/`、`bin/` 前置注入 `env['PATH']`
- 使用 `os.path.isdir(p)` 过滤不存在的路径，跨平台安全

**Phase 8 — 新建 `ui/widgets/class_config_widget.py`**
- `ClassConfigWidget(QWidget)`：3 列 `QTableWidget`（ID 只读 / 名称可编辑 / 颜色按钮）
- 颜色按钮点击弹出 `QColorDialog`，选色后按钮背景实时更新
- `set_num_classes(n)`：自动增减行数，与 `spin_num_classes` 双向联动
- `get_class_config()`：返回 `{'class_names': [...], 'palette': [[r,g,b], ...]}`
- `load_from_advisor(names, palette)`：批量填入，已有手动编辑时弹确认对话框
- 默认 VOC 风格调色板（10 色循环）

**Phase 8 — `ui/main_frame_ui.py`**
- 新增 `from ui.widgets.class_config_widget import ClassConfigWidget`
- 在「数据驱动推荐组」之后插入 `groupBox_classConfig` + `widget_classConfig`

**Phase 7 — `core/framework_adapters/mmseg_trainer.py`**
- `generate_config()` 中在 `num_classes` 注入块之后追加 metainfo 注入块
- 从 `ui_params['class_names']` 和 `ui_params['palette']` 读取，写入三个 dataloader 的 `dataset.metainfo`
- `palette` 长度与 `class_names` 不一致时仅注入 `classes`，不注入 `palette`

**Phase 7 — `scripts/data_source_tree_example.py`**
- `_connect_signals()`：`spin_num_classes.valueChanged` → `widget_classConfig.set_num_classes`；`widget_classConfig.config_changed` → `_on_config_params_changed`
- `_on_generate_recommend_config()`：推荐生成后调用 `widget_classConfig.load_from_advisor(class_names)`
- `_on_start_training()`：读取 `widget_classConfig.get_class_config()` 并写入 `ui_params['class_names']` 和 `ui_params['palette']`

### 测试结果（第二轮）

```
python -m py_compile core\framework_adapters\mmseg_trainer.py \
    ui\widgets\class_config_widget.py \
    ui\main_frame_ui.py \
    scripts\data_source_tree_example.py
→ ALL OK（语法检查通过，无 IDE 诊断错误）
```

---

*文档版本: v2.2 | 第二轮实施完成时间: 2025年*

---

## Phase 7 回归修复 — `PascalVOCDataset` subset 校验冲突

### 问题描述

第二轮 Phase 7 实施后，启动训练时子进程崩溃，报错：

```
ValueError: new classes ('class_0', 'class_1') is not a subset of classes
('background', 'aeroplane', ..., 'tvmonitor') in METAINFO.
```

### 根因分析

1. 基底 config 文件（如 ADE20K 系列）本身携带 `metainfo` 字段
2. `process_segmentation_split()` 将 dataset `type` 强转为 `PascalVOCDataset`（类级 METAINFO = VOC 21 类）
3. config 中残留的 `metainfo.classes`（用户自定义类名）与 VOC 21 类不一致
4. MMSeg 实例化时调用 `BaseSegDataset.get_label_map(old_classes, new_classes)`，要求 `new_classes` 必须是 `old_classes` 的子集，校验失败

**核心语义冲突**：`metainfo.classes` 参数的设计语义是"从大类别集合中选取子集"，而非"任意替换类别"。`PascalVOCDataset` 的类级 METAINFO 是硬编码的 VOC 21 类，无法通过传参方式替换。

### 修复方案

**不修改任何第三方库**，改为在 `work_dir` 动态生成 `custom_rs_dataset.py`，定义 `RSFreeVOCDataset`：

- 继承 `BaseSegDataset`（不继承 `PascalVOCDataset`）
- 类级 `METAINFO` 直接写入用户定义的 `class_names` 和 `palette`
- 支持 VOC 文件树（`JPEGImages/` + `SegmentationClass/` + `ImageSets/`）
- config 中 dataset `type` 改为 `'RSFreeVOCDataset'`，不传 `metainfo` 参数
- 通过 `custom_imports` 注册，`allow_failed_imports=False`（失败立即报错）

### 改动文件：`core/framework_adapters/mmseg_trainer.py`

1. `process_segmentation_split()` 中 `obj['type'] = 'RSFreeVOCDataset'`（原为 `PascalVOCDataset'`），并追加 `obj.pop('metainfo', None)` 清除残留字段
2. 新增 `_write_custom_dataset_file(work_dir, class_names, palette)` 方法，动态生成 `custom_rs_dataset.py`
3. `generate_config()` 中重构 custom_imports 块：同时注册 `custom_live_pred_hook` 和 `custom_rs_dataset`，`allow_failed_imports=False`
4. `class_names` 为空时自动回退为 `['class_0', 'class_1', ...]`（依据 `num_classes`）

### 验收标准

- 生成的 `train_config.py` 中 dataset `type='RSFreeVOCDataset'`，无 `metainfo` 字段
- `work_dir` 中存在 `custom_rs_dataset.py`，`METAINFO` 包含用户类别
- 子进程不再报 subset 错误
- 仍读取 VOC 文件树（`JPEGImages/` / `SegmentationClass/` / `ImageSets/Segmentation/`）

### 测试结果

```
python -m py_compile core\framework_adapters\mmseg_trainer.py
→ OK（语法检查通过，无 IDE 诊断错误）
```

---

*文档版本: v2.3 | Phase 7 回归修复时间: 2026年*
