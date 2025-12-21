# 数据源管理树形控件使用说明

## 功能概述

数据源管理组件已升级为 QTreeWidget，支持从 txt 文件加载样本列表，并提供交互式样本浏览功能。

## 主要特性

### 1. 树形结构
```
📂 训练集 (Train) [10个样本]
   ├── image_0001
   ├── image_0002
   └── ...
📂 验证集 (Val) [3个样本]
   ├── image_0011
   └── ...
📂 测试集 (Test) [2个样本]
   ├── image_0014
   └── ...
```

### 2. UI 配置
- **headerHidden**: true（隐藏列头）
- **selectionMode**: SingleSelection（单选模式）
- **按钮**: "添加样本"（合并了原来的"添加影像"和"添加标签"）

### 3. 数据加载

#### 从 txt 文件加载
点击"添加样本"按钮，选择包含以下文件的目录：
- `train.txt` - 训练集样本列表
- `val.txt` - 验证集样本列表
- `test.txt` - 测试集样本列表

每个 txt 文件格式：
```
image_0001
image_0002
image_0003
...
```

#### 示例数据
项目包含 `example_data/` 目录，内含示例 txt 文件供测试使用。

## 核心类和方法

### DataSourceManager 类

#### 初始化方法
```python
manager = DataSourceManager(tree_widget)
```

#### 主要方法

**加载数据**
```python
# 从 txt 文件加载
manager.load_from_txt_files(data_root)

# 手动添加单个样本
manager.add_sample('train', 'image_0001')

# 批量添加样本
manager.add_samples_batch('train', ['image_0001', 'image_0002'])
```

**查询数据**
```python
# 获取指定数据集的样本
train_samples = manager.get_samples('train')

# 获取所有数据集
all_samples = manager.get_all_samples()
```

**节点判断**
```python
# 判断是否为父节点（Train/Val/Test）
is_parent = manager.is_parent_node(item)

# 判断是否为叶子节点（样本）
is_leaf = manager.is_leaf_node(item)

# 获取样本信息
sample_info = manager.get_sample_info(item)
# 返回: {'sample_id': 'image_0001', 'dataset': 'train'}
```

**清空数据**
```python
# 清空指定数据集
manager.clear_dataset('train')

# 删除选中的样本
manager.remove_selected_sample()
```

## 交互响应

### 信号连接
```python
# 当前项改变事件
tree_widget.currentItemChanged.connect(on_tree_item_changed)

# 项点击事件
tree_widget.itemClicked.connect(on_tree_item_clicked)
```

### 事件处理逻辑

#### 点击父节点
- 显示数据集统计信息
- 在状态栏显示：`数据集: TRAIN | 样本数: 10`

#### 点击叶子节点（样本）
- 提取样本 ID 和所属数据集
- 触发可视化加载：`load_sample_visualization(sample_info)`
- 在状态栏显示：`当前样本: image_0001 | 数据集: TRAIN`

### 示例代码

```python
def on_tree_item_changed(self, current, previous):
    """树控件当前项改变事件"""
    if current is None:
        return
    
    # 判断节点类型
    if self.data_manager.is_parent_node(current):
        # 点击父节点：显示统计信息
        node_data = current.data(0, Qt.ItemDataRole.UserRole)
        dataset = node_data.get('dataset', '')
        count = current.childCount()
        self.statusBar().showMessage(f"数据集: {dataset.upper()} | 样本数: {count}")
        
    elif self.data_manager.is_leaf_node(current):
        # 点击叶子节点：加载样本可视化
        sample_info = self.data_manager.get_sample_info(current)
        if sample_info:
            self.load_sample_visualization(sample_info)

def load_sample_visualization(self, sample_info):
    """加载样本可视化"""
    sample_id = sample_info['sample_id']
    dataset = sample_info['dataset']
    
    # TODO: 实现实际的可视化加载
    # 1. 根据 sample_id 找到影像文件路径
    # 2. 加载影像到 graphicsView_canvas
    # 3. 加载并叠加标签
```

## 数据存储结构

### 节点数据格式

**父节点（Train/Val/Test）**
```python
{
    "type": "parent",
    "dataset": "train"  # 或 "val", "test"
}
```

**叶子节点（样本）**
```python
{
    "type": "leaf",
    "sample_id": "image_0001",
    "dataset": "train"
}
```

## 运行示例

```bash
# 运行示例程序
python data_source_tree_example.py
```

### 测试步骤
1. 启动程序
2. 点击"添加样本"按钮
3. 选择 `example_data/` 目录
4. 查看加载的样本树
5. 点击不同节点，观察状态栏和控制台输出

## 扩展建议

### 1. 可视化加载
在 `load_sample_visualization()` 方法中实现：
- 使用 GDAL/rasterio 加载遥感影像
- 使用 QGraphicsScene 显示影像
- 叠加标签图层

### 2. 右键菜单
添加上下文菜单支持：
- 删除样本
- 移动样本到其他数据集
- 查看样本详细信息

### 3. 拖拽支持
实现样本在不同数据集间的拖拽移动

### 4. 搜索过滤
添加搜索框，支持样本 ID 快速查找

## 注意事项

1. txt 文件必须使用 UTF-8 编码
2. 样本 ID 不应包含特殊字符
3. 大数据集加载可能需要进度条提示
4. 建议对大数据集使用分页或虚拟滚动优化
