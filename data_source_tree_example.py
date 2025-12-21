"""
数据源管理树形控件示例
展示如何初始化和操作 QTreeWidget 来管理 Train/Val/Test 数据集
"""

from PySide6.QtWidgets import QApplication, QMainWindow, QTreeWidgetItem, QFileDialog, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from main_frame_ui import Ui_MainWindow
import sys
import os


class DataSourceManager:
    """数据源管理器 - 负责管理树形控件中的数据"""
    
    def __init__(self, tree_widget):
        self.tree = tree_widget
        self.train_node = None
        self.val_node = None
        self.test_node = None
        self.data_root = None  # 数据根目录
        self._init_tree_structure()
    
    def _init_tree_structure(self):
        """初始化树形结构：创建三个固定的顶级节点"""
        self.tree.clear()
        
        # 创建三个顶级节点
        self.train_node = QTreeWidgetItem(self.tree)
        self.train_node.setText(0, "📂 训练集 (Train) [0个样本]")
        self.train_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "train"})
        
        self.val_node = QTreeWidgetItem(self.tree)
        self.val_node.setText(0, "📂 验证集 (Val) [0个样本]")
        self.val_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "val"})
        
        self.test_node = QTreeWidgetItem(self.tree)
        self.test_node.setText(0, "📂 测试集 (Test) [0个样本]")
        self.test_node.setData(0, Qt.ItemDataRole.UserRole, {"type": "parent", "dataset": "test"})
        
        # 默认展开所有节点
        self.tree.expandAll()
    
    def load_from_txt_files(self, data_root):
        """
        从 train.txt, val.txt, test.txt 加载样本列表
        
        Args:
            data_root: 数据根目录，包含 train.txt, val.txt, test.txt
        """
        self.data_root = data_root
        
        # 清空现有数据
        self.train_node.takeChildren()
        self.val_node.takeChildren()
        self.test_node.takeChildren()
        
        # 加载各个数据集
        datasets = {
            'train': (os.path.join(data_root, 'train.txt'), self.train_node),
            'val': (os.path.join(data_root, 'val.txt'), self.val_node),
            'test': (os.path.join(data_root, 'test.txt'), self.test_node)
        }
        
        for dataset_type, (txt_path, parent_node) in datasets.items():
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            sample_id = line.strip()
                            if sample_id:  # 跳过空行
                                self._add_sample_node(parent_node, sample_id, dataset_type)
                    print(f"✅ 已加载 {dataset_type}: {parent_node.childCount()} 个样本")
                except Exception as e:
                    print(f"❌ 加载 {txt_path} 失败: {e}")
            else:
                print(f"⚠️  文件不存在: {txt_path}")
            
            # 更新计数
            self._update_count(parent_node)
        
        # 展开所有节点
        self.tree.expandAll()
    
    def _add_sample_node(self, parent_node, sample_id, dataset_type):
        """添加样本子节点"""
        child = QTreeWidgetItem(parent_node)
        child.setText(0, sample_id)
        # 存储节点信息：类型为叶子节点，包含样本ID和所属数据集
        child.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "leaf",
            "sample_id": sample_id,
            "dataset": dataset_type
        })
    
    def add_sample(self, dataset_type, sample_id):
        """
        添加样本到指定数据集
        
        Args:
            dataset_type: 'train', 'val', 或 'test'
            sample_id: 样本ID，如 'image_0001'
        """
        # 选择对应的父节点
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node is None:
            print(f"错误：未知的数据集类型 '{dataset_type}'")
            return
        
        # 创建子节点
        self._add_sample_node(parent_node, sample_id, dataset_type)
        
        # 更新父节点的样本计数
        self._update_count(parent_node)
    
    def add_samples_batch(self, dataset_type, sample_ids):
        """批量添加样本"""
        for sample_id in sample_ids:
            self.add_sample(dataset_type, sample_id)
    
    def remove_selected_sample(self):
        """删除当前选中的样本（不能删除顶级节点）"""
        current_item = self.tree.currentItem()
        if current_item is None:
            return
        
        # 检查是否是顶级节点
        parent = current_item.parent()
        if parent is None:
            print("不能删除顶级节点（Train/Val/Test）")
            return
        
        # 删除子节点
        parent.removeChild(current_item)
        self._update_count(parent)
    
    def clear_dataset(self, dataset_type):
        """清空指定数据集的所有样本"""
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node:
            parent_node.takeChildren()  # 移除所有子节点
            self._update_count(parent_node)
    
    def get_samples(self, dataset_type):
        """获取指定数据集的所有样本ID"""
        parent_node = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }.get(dataset_type)
        
        if parent_node is None:
            return []
        
        samples = []
        for i in range(parent_node.childCount()):
            child = parent_node.child(i)
            node_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node_data, dict):
                sample_id = node_data.get('sample_id', '')
            else:
                sample_id = node_data
            samples.append(sample_id)
        
        return samples
    
    def get_all_samples(self):
        """获取所有数据集的样本"""
        return {
            'train': self.get_samples('train'),
            'val': self.get_samples('val'),
            'test': self.get_samples('test')
        }
    
    def _update_count(self, parent_node):
        """更新父节点显示的样本数量"""
        count = parent_node.childCount()
        node_data = parent_node.data(0, Qt.ItemDataRole.UserRole)
        
        if isinstance(node_data, dict):
            dataset_type = node_data.get('dataset', '')
        else:
            dataset_type = node_data
        
        # 更新显示文本
        labels = {
            'train': f"📂 训练集 (Train) [{count}个样本]",
            'val': f"📂 验证集 (Val) [{count}个样本]",
            'test': f"📂 测试集 (Test) [{count}个样本]"
        }
        
        parent_node.setText(0, labels.get(dataset_type, f"未知 [{count}个样本]"))
    
    def is_parent_node(self, item):
        """判断是否为父节点"""
        if item is None:
            return False
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return node_data.get('type') == 'parent'
        return item.parent() is None
    
    def is_leaf_node(self, item):
        """判断是否为叶子节点（样本节点）"""
        if item is None:
            return False
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return node_data.get('type') == 'leaf'
        return item.parent() is not None
    
    def get_sample_info(self, item):
        """
        获取样本节点的信息
        
        Returns:
            dict: {'sample_id': str, 'dataset': str} 或 None
        """
        if not self.is_leaf_node(item):
            return None
        
        node_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(node_data, dict):
            return {
                'sample_id': node_data.get('sample_id', ''),
                'dataset': node_data.get('dataset', '')
            }
        return None


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # 初始化数据源管理器
        self.data_manager = DataSourceManager(self.ui.treeWidget_dataSources)
        
        # 连接信号
        self.ui.pushButton_addSample.clicked.connect(self.on_add_sample)
        
        # 连接树控件的点击信号
        self.ui.treeWidget_dataSources.currentItemChanged.connect(self.on_tree_item_changed)
        self.ui.treeWidget_dataSources.itemClicked.connect(self.on_tree_item_clicked)
        
        # 添加示例数据（可选：注释掉以测试从文件加载）
        # self._load_example_data()
    
    def _load_example_data(self):
        """加载示例数据（用于测试）"""
        # 训练集：8000个样本
        train_samples = [f"image_{i:04d}" for i in range(1, 8001)]
        self.data_manager.add_samples_batch('train', train_samples)
        
        # 验证集：1000个样本
        val_samples = [f"image_{i:04d}" for i in range(8001, 9001)]
        self.data_manager.add_samples_batch('val', val_samples)
        
        # 测试集：1000个样本
        test_samples = [f"image_{i:04d}" for i in range(9001, 10001)]
        self.data_manager.add_samples_batch('test', test_samples)
        
        print("✅ 示例数据加载完成")
        print(f"训练集: {len(self.data_manager.get_samples('train'))} 个样本")
        print(f"验证集: {len(self.data_manager.get_samples('val'))} 个样本")
        print(f"测试集: {len(self.data_manager.get_samples('test'))} 个样本")
    
    def on_add_sample(self):
        """添加样本按钮点击事件 - 从 txt 文件加载数据"""
        # 打开文件夹选择对话框
        data_root = QFileDialog.getExistingDirectory(
            self,
            "选择数据根目录（包含 train.txt, val.txt, test.txt）",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if data_root:
            # 检查必要的文件是否存在
            required_files = ['train.txt', 'val.txt', 'test.txt']
            missing_files = [f for f in required_files if not os.path.exists(os.path.join(data_root, f))]
            
            if missing_files:
                QMessageBox.warning(
                    self,
                    "文件缺失",
                    f"以下文件不存在：\n" + "\n".join(missing_files)
                )
            
            # 加载数据
            self.data_manager.load_from_txt_files(data_root)
            self.statusBar().showMessage(f"已从 {data_root} 加载数据集")
    
    def on_tree_item_changed(self, current, previous):
        """树控件当前项改变事件"""
        if current is None:
            return
        
        # 判断节点类型
        if self.data_manager.is_parent_node(current):
            # 点击父节点：显示统计信息
            node_data = current.data(0, Qt.ItemDataRole.UserRole)
            dataset = node_data.get('dataset', '') if isinstance(node_data, dict) else ''
            count = current.childCount()
            self.statusBar().showMessage(f"数据集: {dataset.upper()} | 样本数: {count}")
            
        elif self.data_manager.is_leaf_node(current):
            # 点击叶子节点：加载样本可视化
            sample_info = self.data_manager.get_sample_info(current)
            if sample_info:
                self.load_sample_visualization(sample_info)
    
    def on_tree_item_clicked(self, item, column):
        """树控件项点击事件"""
        # 这里可以添加额外的点击处理逻辑
        pass
    
    def load_sample_visualization(self, sample_info):
        """
        加载样本可视化
        
        Args:
            sample_info: {'sample_id': str, 'dataset': str}
        """
        sample_id = sample_info['sample_id']
        dataset = sample_info['dataset']
        
        print(f"🖼️  加载样本可视化: {sample_id} (来自 {dataset} 数据集)")
        self.statusBar().showMessage(f"当前样本: {sample_id} | 数据集: {dataset.upper()}")
        
        # TODO: 在这里实现实际的可视化加载逻辑
        # 1. 根据 sample_id 找到对应的影像文件路径
        # 2. 加载影像到 graphicsView_canvas
        # 3. 如果有标签，也加载标签进行叠加显示
        
        # 示例代码框架：
        # if self.data_manager.data_root:
        #     img_path = os.path.join(self.data_manager.data_root, 'images', dataset, f"{sample_id}.tif")
        #     label_path = os.path.join(self.data_manager.data_root, 'labels', dataset, f"{sample_id}.png")
        #     
        #     if os.path.exists(img_path):
        #         # 加载并显示影像
        #         self.display_image(img_path)
        #     
        #     if os.path.exists(label_path):
        #         # 加载并叠加标签
        #         self.overlay_label(label_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
