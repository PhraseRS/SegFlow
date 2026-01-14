"""
数据源管理树形控件示例
展示如何初始化和操作 QTreeWidget 来管理 Train/Val/Test 数据集
支持点击样本显示影像和对应的label影像
"""

from PySide6.QtWidgets import (QApplication, QMainWindow, QTreeWidgetItem, QFileDialog,
                                QMessageBox, QGraphicsScene, QGraphicsPixmapItem, QSplitter,
                                QGraphicsRectItem, QGraphicsLineItem, QListWidgetItem, QLabel)
from PySide6.QtCore import Qt, QRectF, QSize, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen, QBrush
from main_frame_ui import Ui_MainWindow
from dataset_metadata import DatasetMetadataManager
from thumbnail_manager import ThumbnailLazyLoader
from dataset_resplit_dialog import DatasetResplitDialog
import sys
import os
import random


# 视图模式常量
VIEW_MODE_DETAIL = 0
VIEW_MODE_GRID = 1


class SwipeLineItem(QGraphicsLineItem):
    """卷帘分割线"""
    def __init__(self, parent=None):
        super().__init__(parent)
        pen = QPen(QColor(255, 255, 0), 2)  # 黄色线条
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setZValue(100)  # 最上层


class ClippedPixmapItem(QGraphicsPixmapItem):
    """支持裁剪的图像项"""
    def __init__(self, pixmap=None, parent=None):
        super().__init__(pixmap, parent)
        self.clip_rect = None  # 裁剪矩形
    
    def set_clip_rect(self, rect):
        """设置裁剪区域"""
        self.clip_rect = rect
        self.update()
    
    def clear_clip(self):
        """清除裁剪"""
        self.clip_rect = None
        self.update()
    
    def paint(self, painter, option, widget=None):
        if self.clip_rect:
            painter.setClipRect(self.clip_rect)
        super().paint(painter, option, widget)


class ImageViewer:
    """影像查看器 - 负责在 QGraphicsView 中显示影像和标签"""
    
    # VOC标签调色板（与Pascal VOC一致）
    VOC_PALETTE = [
        (0, 0, 0),        # 0: 背景 - 黑色
        (128, 0, 0),      # 1: 深红
        (0, 128, 0),      # 2: 深绿
        (128, 128, 0),    # 3: 橄榄
        (0, 0, 128),      # 4: 深蓝
        (128, 0, 128),    # 5: 紫色
        (0, 128, 128),    # 6: 青色
        (128, 128, 128),  # 7: 灰色
        (64, 0, 0),       # 8: 暗红
        (192, 0, 0),      # 9: 红色
        (64, 128, 0),     # 10: 黄绿
        (192, 128, 0),    # 11: 橙色
        (64, 0, 128),     # 12: 紫罗兰
        (192, 0, 128),    # 13: 粉红
        (64, 128, 128),   # 14: 浅青
        (192, 128, 128),  # 15: 浅粉
        (0, 64, 0),       # 16: 深绿2
        (128, 64, 0),     # 17: 棕色
        (0, 192, 0),      # 18: 亮绿
        (128, 192, 0),    # 19: 黄绿2
        (0, 64, 128),     # 20: 钢蓝
        (255, 255, 255),  # 21+: 白色（边界/忽略）
    ]
    
    def __init__(self, graphics_view):
        self.view = graphics_view
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        
        # 影像图层
        self.image_item = None
        self.label_item = None
        
        # 卷帘对比相关
        self.swipe_enabled = False
        self.swipe_position = 50  # 百分比 (0-100)
        self.swipe_line = None
        self.image_pixmap = None  # 保存原始pixmap用于卷帘
        self.label_pixmap = None
        
        # 当前显示的路径
        self.current_image_path = None
        self.current_label_path = None
        
        # 标签透明度 (0-100)
        self.label_opacity = 70
        
        # 图层可见性
        self.show_image = True
        self.show_label = True
        
        # 设置视图属性
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(self.view.DragMode.ScrollHandDrag)
    
    def load_image(self, image_path):
        """加载影像文件"""
        if not os.path.exists(image_path):
            print(f"⚠️ 影像文件不存在: {image_path}")
            return False
        
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            print(f"⚠️ 无法加载影像: {image_path}")
            return False
        
        # 保存原始pixmap
        self.image_pixmap = pixmap
        
        # 移除旧的影像
        if self.image_item:
            self.scene.removeItem(self.image_item)
        
        # 添加新影像（使用支持裁剪的项）
        self.image_item = ClippedPixmapItem(pixmap)
        self.image_item.setZValue(0)  # 底层
        self.scene.addItem(self.image_item)
        self.image_item.setVisible(self.show_image)
        
        self.current_image_path = image_path
        
        # 适应视图
        self._fit_to_view()
        
        # 如果卷帘模式开启，更新裁剪
        if self.swipe_enabled:
            self._update_swipe_clip()
        
        print(f"✅ 已加载影像: {image_path}")
        return True
    
    def load_label(self, label_path):
        """加载标签影像（自动应用伪彩色）"""
        if not os.path.exists(label_path):
            print(f"⚠️ 标签文件不存在: {label_path}")
            return False
        
        # 加载原始标签图像
        label_image = QImage(label_path)
        if label_image.isNull():
            print(f"⚠️ 无法加载标签: {label_path}")
            return False
        
        # 应用伪彩色映射
        colored_image = self._apply_label_colormap(label_image)
        pixmap = QPixmap.fromImage(colored_image)
        
        # 保存原始pixmap
        self.label_pixmap = pixmap
        
        # 移除旧的标签
        if self.label_item:
            self.scene.removeItem(self.label_item)
        
        # 添加新标签（使用支持裁剪的项）
        self.label_item = ClippedPixmapItem(pixmap)
        self.label_item.setZValue(1)  # 上层
        self.label_item.setOpacity(self.label_opacity / 100.0)
        self.scene.addItem(self.label_item)
        self.label_item.setVisible(self.show_label)
        
        self.current_label_path = label_path
        
        # 如果卷帘模式开启，更新裁剪
        if self.swipe_enabled:
            self._update_swipe_clip()
        
        print(f"✅ 已加载标签（伪彩色）: {label_path}")
        return True
    
    def _apply_label_colormap(self, label_image):
        """
        将标签图像转换为伪彩色图像
        
        Args:
            label_image: QImage，灰度标签图像（像素值为类别索引）
        
        Returns:
            QImage: RGBA格式的伪彩色图像，背景透明
        """
        width = label_image.width()
        height = label_image.height()
        
        # 创建RGBA输出图像
        colored = QImage(width, height, QImage.Format.Format_ARGB32)
        
        for y in range(height):
            for x in range(width):
                # 获取像素值（类别索引）
                pixel = label_image.pixel(x, y)
                # 对于灰度图，取红色通道值作为类别索引
                gray = pixel & 0xFF
                
                # 获取对应颜色
                if gray < len(self.VOC_PALETTE):
                    r, g, b = self.VOC_PALETTE[gray]
                else:
                    # 超出调色板范围，使用白色
                    r, g, b = 255, 255, 255
                
                # 背景类（0）设为透明
                if gray == 0:
                    alpha = 0
                else:
                    alpha = 255
                
                colored.setPixel(x, y, (alpha << 24) | (r << 16) | (g << 8) | b)
        
        return colored
    
    def load_sample(self, image_path, label_path=None):
        """加载样本（影像 + 可选的标签）"""
        self.clear()
        
        image_loaded = self.load_image(image_path)
        
        if label_path:
            self.load_label(label_path)
        
        return image_loaded
    
    def set_label_opacity(self, opacity):
        """设置标签透明度 (0-100)"""
        self.label_opacity = opacity
        if self.label_item:
            self.label_item.setOpacity(opacity / 100.0)
    
    def set_image_visible(self, visible):
        """设置影像可见性"""
        self.show_image = visible
        if self.image_item:
            self.image_item.setVisible(visible)
    
    def set_label_visible(self, visible):
        """设置标签可见性"""
        self.show_label = visible
        if self.label_item:
            self.label_item.setVisible(visible)
    
    def clear(self):
        """清空场景"""
        self.scene.clear()
        self.image_item = None
        self.label_item = None
        self.swipe_line = None
        self.image_pixmap = None
        self.label_pixmap = None
        self.current_image_path = None
        self.current_label_path = None
    
    def _fit_to_view(self):
        """适应视图大小"""
        if self.image_item:
            self.view.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
    
    def zoom_in(self):
        """放大"""
        self.view.scale(1.2, 1.2)
    
    def zoom_out(self):
        """缩小"""
        self.view.scale(1/1.2, 1/1.2)
    
    def fit_to_window(self):
        """适应窗口"""
        self._fit_to_view()
    
    def set_swipe_enabled(self, enabled):
        """启用/禁用卷帘对比模式"""
        self.swipe_enabled = enabled
        
        if enabled:
            # 启用卷帘模式
            # 设置标签不透明
            if self.label_item:
                self.label_item.setOpacity(1.0)
            # 显示两个图层
            if self.image_item:
                self.image_item.setVisible(True)
            if self.label_item:
                self.label_item.setVisible(True)
            # 更新裁剪
            self._update_swipe_clip()
        else:
            # 禁用卷帘模式
            # 清除裁剪
            if self.image_item and isinstance(self.image_item, ClippedPixmapItem):
                self.image_item.clear_clip()
            if self.label_item and isinstance(self.label_item, ClippedPixmapItem):
                self.label_item.clear_clip()
            # 移除分割线
            if self.swipe_line:
                self.scene.removeItem(self.swipe_line)
                self.swipe_line = None
            # 恢复透明度
            if self.label_item:
                self.label_item.setOpacity(self.label_opacity / 100.0)
            # 恢复可见性
            if self.image_item:
                self.image_item.setVisible(self.show_image)
            if self.label_item:
                self.label_item.setVisible(self.show_label)
    
    def set_swipe_position(self, position):
        """设置卷帘位置 (0-100)"""
        self.swipe_position = position
        if self.swipe_enabled:
            self._update_swipe_clip()
    
    def _update_swipe_clip(self):
        """更新卷帘裁剪区域（仅裁剪标签，底图完整显示）"""
        if not self.label_item:
            return
        
        # 获取图像尺寸
        if self.image_pixmap:
            width = self.image_pixmap.width()
            height = self.image_pixmap.height()
        elif self.label_pixmap:
            width = self.label_pixmap.width()
            height = self.label_pixmap.height()
        else:
            return
        
        # 计算分割线位置
        split_x = width * self.swipe_position / 100.0
        
        # 底图完整显示，不裁剪
        if self.image_item and isinstance(self.image_item, ClippedPixmapItem):
            self.image_item.clear_clip()
        
        # 标签只显示分割线右侧部分
        right_rect = QRectF(split_x, 0, width - split_x, height)
        if isinstance(self.label_item, ClippedPixmapItem):
            self.label_item.set_clip_rect(right_rect)
        
        # 更新分割线
        if not self.swipe_line:
            self.swipe_line = SwipeLineItem()
            self.scene.addItem(self.swipe_line)
        
        self.swipe_line.setLine(split_x, 0, split_x, height)


class DataSourceManager:
    """数据源管理器 - 负责管理树形控件中的数据"""
    
    def __init__(self, tree_widget):
        self.tree = tree_widget
        self.train_node = None
        self.val_node = None
        self.test_node = None
        self.data_root = None  # 数据根目录
        self.images_dir = None  # 影像目录
        self.labels_dir = None  # 标签目录
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
        从 train.txt, val.txt, test.txt 加载样本列表（支持VOC格式）
        
        VOC格式：txt文件在 ImageSets/Segmentation/ 目录下
        其他格式：txt文件在根目录下
        
        Args:
            data_root: 数据根目录
        """
        self.data_root = data_root
        
        # 自动检测影像和标签目录
        self._detect_directories()
        
        # 清空现有数据
        self.train_node.takeChildren()
        self.val_node.takeChildren()
        self.test_node.takeChildren()
        
        # VOC格式：ImageSets/Segmentation/train.txt
        voc_txt_dir = os.path.join(data_root, 'ImageSets', 'Segmentation')
        
        # 加载各个数据集（优先VOC格式路径）
        datasets = {
            'train': self.train_node,
            'val': self.val_node,
            'test': self.test_node
        }
        
        # 构建txt文件路径列表
        txt_paths = {}
        for dataset_type in datasets.keys():
            # 优先检查VOC格式路径
            voc_path = os.path.join(voc_txt_dir, f'{dataset_type}.txt')
            root_path = os.path.join(data_root, f'{dataset_type}.txt')
            
            if os.path.exists(voc_path):
                txt_paths[dataset_type] = voc_path
            elif os.path.exists(root_path):
                txt_paths[dataset_type] = root_path
            else:
                txt_paths[dataset_type] = None
        
        # 转换为原有格式
        datasets = {
            'train': (txt_paths['train'], self.train_node),
            'val': (txt_paths['val'], self.val_node),
            'test': (txt_paths['test'], self.test_node)
        }
        
        for dataset_type, (txt_path, parent_node) in datasets.items():
            if txt_path and os.path.exists(txt_path):
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
                print(f"⚠️  {dataset_type}.txt 不存在，跳过")
            
            # 更新计数
            self._update_count(parent_node)
        
        # 展开所有节点
        self.tree.expandAll()
    
    def _detect_directories(self):
        """自动检测影像和标签目录（支持VOC格式）"""
        if not self.data_root:
            return
        
        # VOC格式目录命名
        image_dirs = ['JPEGImages', 'images', 'img', 'image', 'imgs', 'data']
        label_dirs = ['SegmentationClass', 'labels', 'label', 'masks', 'mask', 'annotations', 'ann']
        
        # 检测影像目录
        for dir_name in image_dirs:
            path = os.path.join(self.data_root, dir_name)
            if os.path.isdir(path):
                self.images_dir = path
                print(f"📁 检测到影像目录: {path}")
                break
        
        # 检测标签目录
        for dir_name in label_dirs:
            path = os.path.join(self.data_root, dir_name)
            if os.path.isdir(path):
                self.labels_dir = path
                print(f"📁 检测到标签目录: {path}")
                break
        
        # 如果没有检测到，使用VOC默认路径
        if not self.images_dir:
            self.images_dir = os.path.join(self.data_root, 'JPEGImages')
        if not self.labels_dir:
            self.labels_dir = os.path.join(self.data_root, 'SegmentationClass')
    
    def get_sample_paths(self, sample_id, dataset_type):
        """
        获取样本的影像和标签路径（支持VOC格式）
        
        VOC格式目录结构：
        data_root/
        ├── JPEGImages/          # 所有影像（不分train/val/test子目录）
        │   ├── sample_id.jpg
        │   └── ...
        ├── SegmentationClass/   # 所有标签（不分train/val/test子目录）
        │   ├── sample_id.png
        │   └── ...
        └── ImageSets/Segmentation/
            ├── train.txt
            ├── val.txt
            └── test.txt
        
        Args:
            sample_id: 样本ID
            dataset_type: 数据集类型 ('train', 'val', 'test')
        
        Returns:
            tuple: (image_path, label_path) 或 (None, None)
        """
        if not self.data_root:
            return None, None
        
        # 支持的影像扩展名
        image_exts = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
        label_exts = ['.png', '.tif', '.tiff', '.jpg', '.jpeg', '.bmp']
        
        image_path = None
        label_path = None
        
        # VOC格式：影像和标签都在同一目录下，不分train/val/test子目录
        # 查找影像文件
        search_paths = [
            self.images_dir,  # VOC: JPEGImages/
            os.path.join(self.images_dir, dataset_type),  # 兼容其他格式
        ]
        
        for base_path in search_paths:
            if not os.path.isdir(base_path):
                continue
            for ext in image_exts:
                path = os.path.join(base_path, f"{sample_id}{ext}")
                if os.path.exists(path):
                    image_path = path
                    break
            if image_path:
                break
        
        # 查找标签文件
        search_paths = [
            self.labels_dir,  # VOC: SegmentationClass/
            os.path.join(self.labels_dir, dataset_type),  # 兼容其他格式
        ]
        
        for base_path in search_paths:
            if not os.path.isdir(base_path):
                continue
            for ext in label_exts:
                path = os.path.join(base_path, f"{sample_id}{ext}")
                if os.path.exists(path):
                    label_path = path
                    break
            if label_path:
                break
        
        return image_path, label_path
    
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
        
        # 当前视图模式
        self.current_view_mode = VIEW_MODE_DETAIL
        
        # 初始化数据源管理器
        self.data_manager = DataSourceManager(self.ui.treeWidget_dataSources)
        
        # 初始化元数据管理器
        self.metadata_manager = DatasetMetadataManager()
        
        # 初始化影像查看器
        self.image_viewer = ImageViewer(self.ui.graphicsView_canvas)
        
        # 初始化缩略图懒加载管理器
        self.thumbnail_manager = ThumbnailLazyLoader(self.ui.listWidget_thumbnails, thumbnail_size=120)
        
        # 推理模型相关
        self.inference_model = None  # 加载的推理模型
        
        # 防抖定时器（用于图层设置变化时刷新）
        self._layer_refresh_timer = QTimer()
        self._layer_refresh_timer.setSingleShot(True)
        self._layer_refresh_timer.setInterval(50)  # 50ms 防抖
        self._layer_refresh_timer.timeout.connect(self._do_refresh_layer_settings)
        
        # 连接信号
        self._connect_signals()
        
        # 初始化图层控制
        self._init_layer_controls()
        
        # 初始化视图切换
        self._init_view_switcher()
        
        # 初始化推理配置
        self._init_inference_config()
    
    def _init_view_switcher(self):
        """初始化视图切换器"""
        # 默认显示详情视图
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_DETAIL)
        self.ui.action_detailView.setChecked(True)
        self.ui.action_gridView.setChecked(False)
    
    def _connect_signals(self):
        """连接所有信号"""
        # 添加样本按钮
        self.ui.pushButton_addSample.clicked.connect(self.on_add_sample)
        
        # 数据集概览 - 重新划分按钮
        self.ui.widget_datasetOverview.resplit_clicked.connect(self.on_resplit_dataset)
        
        # 树控件的点击信号
        self.ui.treeWidget_dataSources.currentItemChanged.connect(self.on_tree_item_changed)
        self.ui.treeWidget_dataSources.itemClicked.connect(self.on_tree_item_clicked)
        
        # 图层控制
        self.ui.checkBox_baseImage.stateChanged.connect(self.on_base_image_toggled)
        self.ui.checkBox_overlayPrediction.stateChanged.connect(self.on_overlay_toggled)
        self.ui.checkBox_labelOnly.stateChanged.connect(self.on_label_only_toggled)
        self.ui.slider_opacity.valueChanged.connect(self.on_opacity_changed)
        
        # 卷帘对比
        self.ui.checkBox_swipeCompare.stateChanged.connect(self.on_swipe_toggled)
        self.ui.slider_swipe.valueChanged.connect(self.on_swipe_position_changed)
        
        # 视图控制
        self.ui.action_zoomIn.triggered.connect(self.image_viewer.zoom_in)
        self.ui.action_zoomOut.triggered.connect(self.image_viewer.zoom_out)
        self.ui.action_fitToWindow.triggered.connect(self.image_viewer.fit_to_window)
        
        # 视图切换
        self.ui.action_detailView.triggered.connect(self.on_switch_to_detail_view)
        self.ui.action_gridView.triggered.connect(self.on_switch_to_grid_view)
        
        # 网格视图双击
        self.ui.listWidget_thumbnails.itemDoubleClicked.connect(self.on_thumbnail_double_clicked)
        
        # 健康检查卡片过滤信号
        self.ui.widget_healthCheck.filterRequested.connect(self._on_health_filter_requested)
        self.ui.widget_healthCheck.clearFilterRequested.connect(self.clear_tree_filter)
        
        # 推理配置 - 模型加载区
        self.ui.pushButton_browseConfig.clicked.connect(self._browse_config_file)
        self.ui.pushButton_browseCheckpoint.clicked.connect(self._browse_checkpoint_file)
        self.ui.lineEdit_configFile.textChanged.connect(self._on_config_file_changed)
        self.ui.pushButton_loadModel.clicked.connect(self._load_inference_model)
    
    def _init_layer_controls(self):
        """初始化图层控制"""
        # 设置初始透明度显示
        self.ui.label_opacityValue.setText(f"{self.ui.slider_opacity.value()}%")
        # 设置初始卷帘位置显示
        self.ui.label_swipeValue.setText(f"{self.ui.slider_swipe.value()}%")
    
    def _init_inference_config(self):
        """初始化推理配置"""
        # 检测可用的 CUDA 设备
        cuda_available = self._check_cuda_available()
        
        if cuda_available:
            # 如果 CUDA 可用，默认选择 Auto
            self.ui.comboBox_device.setCurrentIndex(0)  # Auto
            print("🎮 [推理配置] CUDA 可用，默认设备: Auto")
        else:
            # 如果 CUDA 不可用，默认选择 CPU，并禁用 CUDA 选项
            self.ui.comboBox_device.setCurrentIndex(2)  # CPU
            # 禁用 CUDA:0 选项
            model = self.ui.comboBox_device.model()
            item = model.item(1)  # CUDA:0 是索引 1
            if item:
                item.setEnabled(False)
                item.setToolTip("CUDA 不可用")
            print("⚠️  [推理配置] CUDA 不可用，默认设备: CPU")
    
    def _check_cuda_available(self) -> bool:
        """检测 CUDA 是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            # PyTorch 未安装
            return False
        except Exception:
            return False
    
    def on_add_sample(self):
        """添加样本按钮点击事件 - 从VOC格式数据集加载"""
        # 打开文件夹选择对话框
        data_root = QFileDialog.getExistingDirectory(
            self,
            "选择VOC格式数据集根目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not data_root:
            return
        
        # 验证VOC格式结构
        is_valid, error_msg = self._validate_voc_structure(data_root)
        
        if not is_valid:
            QMessageBox.critical(
                self,
                "目录结构错误",
                f"所选目录不是有效的VOC格式数据集。\n\n{error_msg}\n\n"
                f"VOC格式要求的目录结构：\n"
                f"├── JPEGImages/          (影像目录)\n"
                f"├── SegmentationClass/   (标签目录)\n"
                f"└── ImageSets/\n"
                f"    └── Segmentation/\n"
                f"        ├── train.txt\n"
                f"        ├── val.txt\n"
                f"        └── test.txt (可选)"
            )
            return
        
        # 保存数据根目录
        self._current_data_root = data_root
        
        # 加载数据
        self.data_manager.load_from_txt_files(data_root)
        self.statusBar().showMessage(f"已从 {data_root} 加载VOC数据集")
        
        # 更新数据集概览（基本统计）
        self._update_dataset_overview()
        
        # 使用 AnalysisPanel 智能启动统计流程
        self._initialize_analysis_panel(data_root)
    
    def _initialize_analysis_panel(self, data_root):
        """使用 AnalysisPanel 智能启动统计流程"""
        # 收集样本信息
        samples_info = []
        for dataset_type in ['train', 'val', 'test']:
            for sample_id in self.data_manager.get_samples(dataset_type):
                samples_info.append((sample_id, dataset_type))
        
        # 连接 AnalysisPanel 信号
        self.ui.analysis_panel.analysis_started.connect(self._on_analysis_started)
        self.ui.analysis_panel.analysis_finished.connect(self._on_analysis_finished)
        self.ui.analysis_panel.analysis_error.connect(self._on_analysis_error)
        
        # 启动智能分析流程
        labels_dir = self.data_manager.labels_dir
        self.ui.analysis_panel.initialize_statistics_flow(
            data_root, 
            samples_info, 
            labels_dir
        )
    
    def on_resplit_dataset(self):
        """重新划分数据集"""
        # 获取当前数据集统计
        train_count = len(self.data_manager.get_samples('train'))
        val_count = len(self.data_manager.get_samples('val'))
        test_count = len(self.data_manager.get_samples('test'))
        
        if train_count + val_count + test_count == 0:
            QMessageBox.warning(self, "无数据", "请先加载数据集")
            return
        
        # 创建并显示重新划分对话框
        dialog = DatasetResplitDialog(train_count, val_count, test_count, self)
        dialog.resplit_confirmed.connect(self._perform_resplit)
        dialog.exec()
    
    def _perform_resplit(self, mode, params):
        """执行数据集重新划分
        
        Args:
            mode: 'auto' 或 'custom'
            params: 划分参数字典
        """
        # 收集所有样本
        all_samples = []
        for dataset_type in ['train', 'val', 'test']:
            samples = self.data_manager.get_samples(dataset_type)
            all_samples.extend(samples)
        
        total_samples = len(all_samples)
        
        if mode == 'auto':
            # 自动化划分
            train_ratio = params['train_ratio']
            val_ratio = params['val_ratio']
            test_ratio = params['test_ratio']
            shuffle = params['shuffle']
            seed = params['seed']
            
            # 随机打乱
            if shuffle:
                random.seed(seed)
                random.shuffle(all_samples)
            
            # 计算划分点
            train_count = int(total_samples * train_ratio)
            val_count = int(total_samples * val_ratio)
            
            train_samples = all_samples[:train_count]
            val_samples = all_samples[train_count:train_count + val_count]
            test_samples = all_samples[train_count + val_count:]
            
            print(f"✅ 自动划分: Train={len(train_samples)}, Val={len(val_samples)}, Test={len(test_samples)}")
            
        else:
            # 自定义划分
            train_count = params['train_count']
            val_count = params['val_count']
            test_count = params['test_count']
            
            # 简单按顺序划分（也可以添加随机选项）
            train_samples = all_samples[:train_count]
            val_samples = all_samples[train_count:train_count + val_count]
            test_samples = all_samples[train_count + val_count:]
            
            print(f"✅ 自定义划分: Train={len(train_samples)}, Val={len(val_samples)}, Test={len(test_samples)}")
        
        # 清空现有数据集
        self.data_manager.clear_dataset('train')
        self.data_manager.clear_dataset('val')
        self.data_manager.clear_dataset('test')
        
        # 重新添加样本
        for sample_id in train_samples:
            self.data_manager.add_sample('train', sample_id)
        for sample_id in val_samples:
            self.data_manager.add_sample('val', sample_id)
        for sample_id in test_samples:
            self.data_manager.add_sample('test', sample_id)
        
        # 更新数据集概览
        self._update_dataset_overview()
        
        # 保存到 txt 文件（如果有数据根目录）
        if hasattr(self, '_current_data_root') and self._current_data_root:
            self._save_split_to_txt()
        
        self.statusBar().showMessage("数据集重新划分完成")
        QMessageBox.information(
            self,
            "划分完成",
            f"数据集已重新划分:\n"
            f"Train: {len(train_samples)} 样本\n"
            f"Val: {len(val_samples)} 样本\n"
            f"Test: {len(test_samples)} 样本"
        )
    
    def _save_split_to_txt(self):
        """保存划分结果到 txt 文件"""
        if not hasattr(self, '_current_data_root') or not self._current_data_root:
            return
        
        # VOC格式路径
        txt_dir = os.path.join(self._current_data_root, 'ImageSets', 'Segmentation')
        
        # 如果目录不存在，创建它
        os.makedirs(txt_dir, exist_ok=True)
        
        # 保存各个数据集
        for dataset_type in ['train', 'val', 'test']:
            samples = self.data_manager.get_samples(dataset_type)
            txt_path = os.path.join(txt_dir, f'{dataset_type}.txt')
            
            try:
                with open(txt_path, 'w', encoding='utf-8') as f:
                    for sample_id in samples:
                        f.write(f"{sample_id}\n")
                print(f"✅ 已保存 {dataset_type}.txt ({len(samples)} 样本)")
            except Exception as e:
                print(f"❌ 保存 {txt_path} 失败: {e}")

    
    def _on_analysis_started(self):
        """分析开始回调"""
        self.statusBar().showMessage("正在分析数据集...")
    
    def _on_analysis_finished(self):
        """分析完成回调"""
        self.statusBar().showMessage("数据集分析完成")
        self._on_metadata_ready()
    
    def _on_analysis_error(self, error_msg):
        """分析错误回调"""
        self.statusBar().showMessage(f"分析错误: {error_msg}")
        print(f"⚠️ 分析错误: {error_msg}")
    
    def _load_or_calculate_metadata(self, data_root):
        """加载缓存的元数据，或启动后台进程计算（保留用于兼容）"""
        # 初始化数据库
        self.metadata_manager.init_database(data_root)
        
        # 收集样本信息
        samples_info = []
        for dataset_type in ['train', 'val', 'test']:
            for sample_id in self.data_manager.get_samples(dataset_type):
                samples_info.append((sample_id, dataset_type))
        
        # 连接信号
        self.metadata_manager.signals.progress.connect(self._on_metadata_progress)
        self.metadata_manager.signals.finished.connect(self._on_metadata_finished)
        self.metadata_manager.signals.error.connect(self._on_metadata_error)
        
        # 检查缓存是否有效
        if self.metadata_manager.is_cache_valid(samples_info):
            print("✅ 使用缓存的元数据")
            self.statusBar().showMessage("已加载元数据缓存")
            self._on_metadata_ready()
            return
        
        # 缓存无效，启动后台进程计算
        print("🔄 启动后台进程计算元数据...")
        self.statusBar().showMessage("正在计算数据集统计信息（后台进程）...")
        
        labels_dir = self.data_manager.labels_dir
        self.metadata_manager.start_calculation(samples_info, labels_dir)
    
    def _on_metadata_progress(self, current, total, sample_id):
        """元数据计算进度回调（已在后端降频，约每50-100个样本触发一次）"""
        self.statusBar().showMessage(f"正在分析样本... {current}/{total} ({sample_id})")
        # 更新统计面板（从数据库读取，毫秒级）
        self._on_metadata_ready()
    
    def _on_metadata_finished(self):
        """元数据计算完成回调"""
        self.statusBar().showMessage("数据集分析完成")
        self._on_metadata_ready()
    
    def _on_metadata_error(self, error_msg):
        """元数据计算错误回调"""
        print(f"⚠️ 元数据计算错误: {error_msg}")
    
    def _on_metadata_ready(self):
        """元数据准备就绪，更新UI（从数据库读取）"""
        # 优先从 AnalysisPanel 获取统计数据
        stats = self.ui.analysis_panel.get_aggregated_stats()
        if not stats:
            # 回退到直接从 metadata_manager 获取
            stats = self.metadata_manager.get_aggregated_stats()
        
        if stats:
            # 1. 更新类别分布（传递 image_counts）
            self._update_class_distribution(
                stats.get('class_distribution', {}),
                stats.get('image_counts', {})
            )
            # 2. 更新覆盖率分析
            self._update_coverage_analysis()
            # 3. 更新健康检查
            self._update_health_check()
            # 4. 更新尺度分析
            self._update_scale_analysis(stats.get('size_stats', {}))
    
    def _update_class_distribution(self, class_distribution, image_counts=None):
        """更新类别分布面板
        
        Args:
            class_distribution: 各类别像素总数 {class_id: pixel_count}
            image_counts: 各类别出现在多少张图像中 {class_id: image_count}
        """
        if not class_distribution:
            self.ui.widget_classDistribution.clear()
            return
        
        # 按类别ID排序
        sorted_classes = sorted(class_distribution.items(), 
                                key=lambda x: int(x[0]))
        
        # 准备数据格式
        class_vals = [str(k) for k, v in sorted_classes]
        pixel_counts = [int(v) for k, v in sorted_classes]
        
        # 使用真实的 image_counts（如果提供），否则默认为0
        if image_counts:
            img_counts = [int(image_counts.get(k, 0)) for k, v in sorted_classes]
        else:
            img_counts = [0] * len(class_vals)
        
        stats = {
            'class_vals': class_vals,
            'pixel_counts': pixel_counts,
            'image_counts': img_counts
        }
        
        self.ui.widget_classDistribution.set_data(stats)
    
    def _update_scale_analysis(self, size_stats):
        """更新尺度分析面板"""
        widths = size_stats.get('widths', [])
        heights = size_stats.get('heights', [])
        
        if not widths or not heights:
            self.ui.label_scaleAnalysis.setText("影像尺寸统计:\n- 暂无数据")
            return
        
        min_w = size_stats.get('min_width', 0)
        min_h = size_stats.get('min_height', 0)
        max_w = size_stats.get('max_width', 0)
        max_h = size_stats.get('max_height', 0)
        
        avg_w = sum(widths) / len(widths) if widths else 0
        avg_h = sum(heights) / len(heights) if heights else 0
        
        text = (
            f"影像尺寸统计:\n"
            f"- 最小: {min_w} × {min_h}\n"
            f"- 最大: {max_w} × {max_h}\n"
            f"- 平均: {avg_w:.0f} × {avg_h:.0f}\n"
            f"- 样本数: {len(widths)}"
        )
        self.ui.label_scaleAnalysis.setText(text)
    
    def _update_coverage_analysis(self):
        """更新覆盖率分析面板"""
        # 从 AnalysisPanel 的 metadata_manager 获取数据库
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            self.ui.widget_coverageAnalysis.clear()
            return
        
        image_records = database.get_image_records()
        if not image_records:
            self.ui.widget_coverageAnalysis.clear()
            return
        
        self.ui.widget_coverageAnalysis.set_data(image_records)
    
    def _update_health_check(self):
        """更新健康检查面板"""
        # 从 AnalysisPanel 的 metadata_manager 获取数据库
        database = self.ui.analysis_panel.metadata_manager.database
        if database is None:
            self.ui.widget_healthCheck.clear()
            return
        
        # 获取健康检查问题汇总
        health_data = database.get_health_check_issues()
        if not health_data:
            self.ui.widget_healthCheck.clear()
            return
        
        # 提取问题数据
        issues = {
            'fatal': health_data.get('fatal', {}),
            'warning': health_data.get('warning', {})
        }
        total_samples = health_data.get('total_samples', 0)
        
        self.ui.widget_healthCheck.set_issues(issues, total_samples)
    
    def _on_health_filter_requested(self, issue_type: str):
        """健康检查过滤请求处理"""
        # 获取问题文件列表
        files = self.ui.widget_healthCheck.get_files_by_issue(issue_type)
        if not files:
            return
        
        # 过滤树形控件，只显示有问题的样本
        self._filter_tree_by_files(files)
    
    def _filter_tree_by_files(self, file_list):
        """根据文件列表过滤树形控件"""
        # 隐藏所有不在列表中的样本
        for dataset_type in ['train', 'val', 'test']:
            parent_node = {
                'train': self.data_manager.train_node,
                'val': self.data_manager.val_node,
                'test': self.data_manager.test_node
            }.get(dataset_type)
            
            if not parent_node:
                continue
            
            for i in range(parent_node.childCount()):
                child = parent_node.child(i)
                sample_info = self.data_manager.get_sample_info(child)
                if sample_info:
                    sample_id = sample_info['sample_id']
                    # 检查样本是否在问题列表中
                    child.setHidden(sample_id not in file_list)
    
    def clear_tree_filter(self):
        """清除树形控件过滤"""
        # 显示所有样本
        for dataset_type in ['train', 'val', 'test']:
            parent_node = {
                'train': self.data_manager.train_node,
                'val': self.data_manager.val_node,
                'test': self.data_manager.test_node
            }.get(dataset_type)
            
            if not parent_node:
                continue
            
            for i in range(parent_node.childCount()):
                child = parent_node.child(i)
                child.setHidden(False)
    
    def _update_dataset_overview(self):
        """更新数据集概览面板"""
        train_count = len(self.data_manager.get_samples('train'))
        val_count = len(self.data_manager.get_samples('val'))
        test_count = len(self.data_manager.get_samples('test'))
        
        self.ui.widget_datasetOverview.update_data(train_count, val_count, test_count)
    
    def _validate_voc_structure(self, data_root):
        """
        验证目录是否为有效的VOC格式结构（仅检查第一级目录）
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        errors = []
        
        # 检查第一级目录中必须存在的目录
        # 1. JPEGImages 目录
        jpeg_dir = os.path.join(data_root, 'JPEGImages')
        if not os.path.isdir(jpeg_dir):
            errors.append("缺少 JPEGImages 目录（影像目录）")
        
        # 2. SegmentationClass 目录
        seg_dir = os.path.join(data_root, 'SegmentationClass')
        if not os.path.isdir(seg_dir):
            errors.append("缺少 SegmentationClass 目录（标签目录）")
        
        # 3. ImageSets 目录
        imagesets_dir = os.path.join(data_root, 'ImageSets')
        if not os.path.isdir(imagesets_dir):
            errors.append("缺少 ImageSets 目录")
        else:
            # 检查 ImageSets/Segmentation 目录
            seg_sets_dir = os.path.join(imagesets_dir, 'Segmentation')
            if not os.path.isdir(seg_sets_dir):
                errors.append("缺少 ImageSets/Segmentation 目录")
            else:
                # 检查至少存在 train.txt 或 val.txt
                train_txt = os.path.join(seg_sets_dir, 'train.txt')
                val_txt = os.path.join(seg_sets_dir, 'val.txt')
                
                if not os.path.isfile(train_txt) and not os.path.isfile(val_txt):
                    errors.append("ImageSets/Segmentation/ 中缺少 train.txt 和 val.txt")
        
        if errors:
            return False, "\n".join(f"• {e}" for e in errors)
        
        return True, ""
    
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
            
            # 如果在网格视图模式，过滤显示该数据集的样本
            if self.current_view_mode == VIEW_MODE_GRID:
                self._filter_grid_by_dataset(dataset)
            
        elif self.data_manager.is_leaf_node(current):
            # 点击叶子节点：加载样本可视化
            sample_info = self.data_manager.get_sample_info(current)
            if sample_info:
                # 如果在网格视图，切换到详情视图
                if self.current_view_mode == VIEW_MODE_GRID:
                    self.on_switch_to_detail_view()
                self.load_sample_visualization(sample_info)
    
    def _filter_grid_by_dataset(self, dataset_type):
        """根据数据集类型过滤网格视图（懒加载模式）"""
        # 清空现有内容
        self.thumbnail_manager.clear()
        
        # 只获取指定数据集的样本
        if dataset_type:
            samples = self.data_manager.get_samples(dataset_type)
            
            if not samples:
                self.statusBar().showMessage(f"{dataset_type.upper()}: 无样本")
                return
            
            # 添加样本（只创建占位项）
            for sample_id in samples:
                image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset_type)
                key = f"{dataset_type}_{sample_id}"
                self.thumbnail_manager.add_sample(key, sample_id, dataset_type, image_path, label_path)
            
            self.statusBar().showMessage(f"{dataset_type.upper()}: 共 {len(samples)} 个样本")
            
            # 触发初始加载（只加载可见区域）
            self.thumbnail_manager.trigger_initial_load()
    
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
        
        # 获取影像和标签路径
        image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset)
        
        if image_path:
            # 加载影像和标签
            self.image_viewer.load_sample(image_path, label_path)
            
            # 更新状态栏
            status_msg = f"当前样本: {sample_id} | 数据集: {dataset.upper()}"
            if label_path:
                status_msg += " | 已加载标签"
            else:
                status_msg += " | 无标签"
            self.statusBar().showMessage(status_msg)
        else:
            # 没有找到影像文件
            self.image_viewer.clear()
            self.statusBar().showMessage(f"⚠️ 未找到样本 {sample_id} 的影像文件")
            
            # 显示提示信息
            QMessageBox.information(
                self,
                "提示",
                f"未找到样本 '{sample_id}' 的影像文件。\n\n"
                f"请确保数据目录结构正确：\n"
                f"- images/{dataset}/{sample_id}.tif\n"
                f"- labels/{dataset}/{sample_id}.png\n\n"
                f"或者：\n"
                f"- images/{sample_id}.tif\n"
                f"- labels/{sample_id}.png"
            )
    
    def on_base_image_toggled(self, state):
        """底图可见性切换"""
        self.image_viewer.set_image_visible(state == Qt.CheckState.Checked.value)
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def on_overlay_toggled(self, state):
        """叠加层可见性切换"""
        self.image_viewer.set_label_visible(state == Qt.CheckState.Checked.value)
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def on_label_only_toggled(self, state):
        """单独显示标签切换"""
        if state == Qt.CheckState.Checked.value:
            # 勾选Label Only：隐藏底图，显示标签，透明度设为100%
            self.ui.checkBox_baseImage.setChecked(False)
            self.ui.checkBox_overlayPrediction.setChecked(True)
            self.ui.slider_opacity.setValue(100)
        else:
            # 取消勾选：恢复默认显示
            self.ui.checkBox_baseImage.setChecked(True)
            self.ui.slider_opacity.setValue(70)
        # 网格视图模式下刷新缩略图（由于上面的setChecked会触发各自的toggled事件，这里不需要额外刷新）
    
    def on_opacity_changed(self, value):
        """透明度滑块变化"""
        self.image_viewer.set_label_opacity(value)
        self.ui.label_opacityValue.setText(f"{value}%")
        # 网格视图模式下刷新缩略图
        if self.current_view_mode == VIEW_MODE_GRID:
            self._schedule_layer_refresh()
    
    def _schedule_layer_refresh(self):
        """调度图层刷新（防抖）"""
        self._layer_refresh_timer.start()
    
    def _do_refresh_layer_settings(self):
        """执行图层设置刷新"""
        show_image = self.ui.checkBox_baseImage.isChecked()
        show_label = self.ui.checkBox_overlayPrediction.isChecked()
        opacity = self.ui.slider_opacity.value()
        self.thumbnail_manager.set_layer_settings(show_image, show_label, opacity)
    
    def on_swipe_toggled(self, state):
        """卷帘对比模式切换"""
        enabled = state == Qt.CheckState.Checked.value
        self.ui.slider_swipe.setEnabled(enabled)
        self.image_viewer.set_swipe_enabled(enabled)
        
        if enabled:
            # 禁用其他图层控制选项
            self.ui.checkBox_baseImage.setEnabled(False)
            self.ui.checkBox_overlayPrediction.setEnabled(False)
            self.ui.checkBox_labelOnly.setEnabled(False)
            self.ui.slider_opacity.setEnabled(False)
        else:
            # 恢复其他图层控制选项
            self.ui.checkBox_baseImage.setEnabled(True)
            self.ui.checkBox_overlayPrediction.setEnabled(True)
            self.ui.checkBox_labelOnly.setEnabled(True)
            self.ui.slider_opacity.setEnabled(True)
    
    def on_swipe_position_changed(self, value):
        """卷帘位置滑块变化"""
        self.image_viewer.set_swipe_position(value)
        self.ui.label_swipeValue.setText(f"{value}%")
    
    def on_switch_to_detail_view(self):
        """切换到详情视图"""
        self.current_view_mode = VIEW_MODE_DETAIL
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_DETAIL)
        self.ui.action_detailView.setChecked(True)
        self.ui.action_gridView.setChecked(False)
        
        # 启用卷帘对比功能
        self.ui.checkBox_swipeCompare.setEnabled(True)
        
        self.statusBar().showMessage("已切换到详情视图")
    
    def on_switch_to_grid_view(self):
        """切换到网格视图"""
        self.current_view_mode = VIEW_MODE_GRID
        self.ui.stackedWidget_views.setCurrentIndex(VIEW_MODE_GRID)
        self.ui.action_gridView.setChecked(True)
        self.ui.action_detailView.setChecked(False)
        
        # 禁用卷帘对比功能（网格视图下不可用）
        self.ui.checkBox_swipeCompare.setEnabled(False)
        self.ui.slider_swipe.setEnabled(False)
        
        # 初始化图层设置
        show_image = self.ui.checkBox_baseImage.isChecked()
        show_label = self.ui.checkBox_overlayPrediction.isChecked()
        opacity = self.ui.slider_opacity.value()
        self.thumbnail_manager.set_layer_settings(show_image, show_label, opacity)
        
        # 加载缩略图（懒加载模式）
        self._populate_grid_view()
    
    def _populate_grid_view(self):
        """填充网格视图（只创建占位项，懒加载缩略图）"""
        # 清空现有内容
        self.thumbnail_manager.clear()
        
        # 收集所有样本信息
        all_samples = self.data_manager.get_all_samples()
        total = sum(len(samples) for samples in all_samples.values())
        
        if total == 0:
            self.statusBar().showMessage("网格视图: 无样本")
            return
        
        # 添加所有样本（只创建占位项）
        for dataset_type, samples in all_samples.items():
            for sample_id in samples:
                image_path, label_path = self.data_manager.get_sample_paths(sample_id, dataset_type)
                key = f"{dataset_type}_{sample_id}"
                self.thumbnail_manager.add_sample(key, sample_id, dataset_type, image_path, label_path)
        
        self.statusBar().showMessage(f"网格视图: 共 {total} 个样本")
        
        # 触发初始加载（只加载可见区域）
        self.thumbnail_manager.trigger_initial_load()
    
    def on_thumbnail_double_clicked(self, item):
        """缩略图双击事件 - 切换到详情视图并显示该样本"""
        sample_info = item.data(Qt.ItemDataRole.UserRole)
        if sample_info:
            # 切换到详情视图
            self.on_switch_to_detail_view()
            
            # 在树形控件中定位到该样本
            self._select_sample_in_tree(sample_info['sample_id'], sample_info['dataset'])
            
            # 加载样本
            self.load_sample_visualization(sample_info)
    
    def _select_sample_in_tree(self, sample_id, dataset_type):
        """在树形控件中选中指定样本"""
        # 获取对应的父节点
        parent_node = {
            'train': self.data_manager.train_node,
            'val': self.data_manager.val_node,
            'test': self.data_manager.test_node
        }.get(dataset_type)
        
        if not parent_node:
            return
        
        # 遍历子节点查找匹配的样本
        for i in range(parent_node.childCount()):
            child = parent_node.child(i)
            node_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(node_data, dict) and node_data.get('sample_id') == sample_id:
                # 展开父节点
                parent_node.setExpanded(True)
                # 选中该节点
                self.ui.treeWidget_dataSources.setCurrentItem(child)
                # 滚动到中间位置
                self.ui.treeWidget_dataSources.scrollToItem(
                    child, 
                    self.ui.treeWidget_dataSources.ScrollHint.PositionAtCenter
                )
                break
    
    # ========================================
    # 推理配置相关方法
    # ========================================
    
    def _browse_config_file(self):
        """浏览并选择MMSeg配置文件"""
        from config_parser import parse_mmseg_config
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 MMSegmentation 配置文件",
            "",
            "Python Files (*.py);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        # 设置配置文件路径
        self.ui.lineEdit_configFile.setText(file_path)
        
        # 验证配置文件格式
        if not self._validate_config_file(file_path):
            return
        
        # 自动解析模型名称
        try:
            config_info = parse_mmseg_config(file_path)
            model_name = config_info['model_name']
            
            # 更新模型名称显示
            self.ui.label_modelNameValue.setText(model_name)
            self.ui.label_modelNameValue.setStyleSheet("color: #000; font-style: normal; font-weight: bold;")
            
            # 输出详细信息
            print(f"✅ [推理配置] 已加载配置文件: {os.path.basename(file_path)}")
            print(f"   📝 模型名称: {model_name}")
            if config_info.get('model_type'):
                print(f"   🏗️  模型类型: {config_info['model_type']}")
            if config_info.get('backbone'):
                print(f"   🔧 Backbone: {config_info['backbone']}")
            if config_info.get('num_classes'):
                print(f"   🎯 类别数: {config_info['num_classes']}")
            
            # 智能推荐权重文件
            self._suggest_checkpoint_file(file_path, model_name)
            
        except Exception as e:
            self.ui.label_modelNameValue.setText("解析失败")
            self.ui.label_modelNameValue.setStyleSheet("color: #f00; font-style: italic;")
            print(f"❌ [推理配置] 配置文件解析失败: {e}")
            QMessageBox.warning(
                self,
                "配置文件解析失败",
                f"无法解析配置文件，可能不是有效的 MMSegmentation 配置。\n\n错误信息: {e}"
            )
    
    def _validate_config_file(self, file_path: str) -> bool:
        """验证配置文件格式"""
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否包含基本的配置关键字
            required_keywords = ['model', 'dict']
            has_keywords = any(keyword in content for keyword in required_keywords)
            
            if not has_keywords:
                QMessageBox.warning(
                    self,
                    "配置文件格式错误",
                    "所选文件可能不是有效的 MMSegmentation 配置文件。\n\n"
                    "有效的配置文件应包含 'model' 定义。"
                )
                return False
            
            return True
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "文件读取错误",
                f"无法读取配置文件。\n\n错误信息: {e}"
            )
            return False
    
    def _suggest_checkpoint_file(self, config_path: str, model_name: str):
        """智能推荐权重文件"""
        # 获取配置文件所在目录
        config_dir = os.path.dirname(config_path)
        
        # 可能的权重文件位置
        search_dirs = [
            config_dir,  # 配置文件同目录
            os.path.join(config_dir, 'checkpoints'),  # checkpoints 子目录
            os.path.join(config_dir, '..', 'checkpoints'),  # 上级目录的 checkpoints
            os.path.join(config_dir, 'work_dirs'),  # work_dirs 目录
        ]
        
        # 搜索匹配的权重文件
        found_checkpoints = []
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            
            try:
                for file in os.listdir(search_dir):
                    if file.endswith(('.pth', '.pt')):
                        # 检查文件名是否与模型名称相关
                        file_lower = file.lower()
                        model_lower = model_name.lower().replace('-', '').replace(' ', '')
                        
                        if model_lower in file_lower.replace('-', '').replace('_', ''):
                            found_checkpoints.append(os.path.join(search_dir, file))
            except:
                continue
        
        # 如果找到匹配的权重文件
        if found_checkpoints:
            # 选择最新的文件（按修改时间）
            latest_checkpoint = max(found_checkpoints, key=os.path.getmtime)
            
            # 询问用户是否使用推荐的权重文件
            reply = QMessageBox.question(
                self,
                "发现匹配的权重文件",
                f"找到与模型 '{model_name}' 匹配的权重文件：\n\n"
                f"{os.path.basename(latest_checkpoint)}\n\n"
                f"是否使用此权重文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.ui.lineEdit_checkpointFile.setText(latest_checkpoint)
                print(f"💡 [推理配置] 自动选择权重文件: {os.path.basename(latest_checkpoint)}")
    
    def _browse_checkpoint_file(self):
        """浏览并选择模型权重文件"""
        # 获取起始目录（如果已选择配置文件，从配置文件目录开始）
        start_dir = ""
        config_path = self.ui.lineEdit_configFile.text()
        if config_path and os.path.exists(config_path):
            start_dir = os.path.dirname(config_path)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择模型权重文件",
            start_dir,
            "PyTorch Checkpoint (*.pth *.pt);;All Files (*.*)"
        )
        
        if file_path:
            self.ui.lineEdit_checkpointFile.setText(file_path)
            
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
            
            print(f"✅ [推理配置] 已选择权重文件: {os.path.basename(file_path)}")
            print(f"   📦 文件大小: {size_mb:.2f} MB")
    
    def _on_config_file_changed(self, text):
        """配置文件路径变化时触发"""
        if not text:
            # 清空时重置模型名称显示
            self.ui.label_modelNameValue.setText("未加载配置")
            self.ui.label_modelNameValue.setStyleSheet("color: #888; font-style: italic;")
    
    def _load_inference_model(self):
        """加载推理模型"""
        # 验证必要的文件是否已选择
        config_path = self.ui.lineEdit_configFile.text().strip()
        checkpoint_path = self.ui.lineEdit_checkpointFile.text().strip()
        
        if not config_path:
            self._log_to_bottom("⚠️  请先选择配置文件")
            QMessageBox.warning(self, "缺少配置文件", "请先选择 MMSegmentation 配置文件。")
            return
        
        if not checkpoint_path:
            self._log_to_bottom("⚠️  请先选择权重文件")
            QMessageBox.warning(self, "缺少权重文件", "请先选择模型权重文件。")
            return
        
        # 验证文件是否存在
        if not os.path.exists(config_path):
            self._log_to_bottom(f"❌ 配置文件不存在: {config_path}")
            QMessageBox.critical(self, "配置文件不存在", f"配置文件不存在:\n{config_path}")
            return
        
        if not os.path.exists(checkpoint_path):
            self._log_to_bottom(f"❌ 权重文件不存在: {checkpoint_path}")
            QMessageBox.critical(self, "权重文件不存在", f"权重文件不存在:\n{checkpoint_path}")
            return
        
        # 获取选择的设备
        device_text = self.ui.comboBox_device.currentText()
        device_map = {
            "Auto": "cuda:0",
            "CUDA:0": "cuda:0",
            "CPU": "cpu"
        }
        device = device_map.get(device_text, "cpu")
        
        # 如果选择 Auto，检测 CUDA 可用性
        if device_text == "Auto":
            if not self._check_cuda_available():
                device = "cpu"
        
        # 更新 UI 状态 - 开始加载
        self.ui.pushButton_loadModel.setEnabled(False)
        self._log_to_bottom("🔄 正在加载模型...")
        
        # 强制刷新 UI
        QApplication.processEvents()
        
        # 使用 QTimer 延迟执行实际加载，避免阻塞 UI
        QTimer.singleShot(100, lambda: self._do_load_inference_model(config_path, checkpoint_path, device))
    
    def _do_load_inference_model(self, config_path: str, checkpoint_path: str, device: str):
        """实际执行模型加载（在延迟后执行）"""
        try:
            # 这里是模型加载的占位符
            # 实际项目中需要使用 MMSegmentation 的 API 加载模型
            # 例如:
            # from mmseg.apis import init_model
            # self.inference_model = init_model(config_path, checkpoint_path, device=device)
            
            # 模拟加载过程（实际使用时删除这部分）
            import time
            time.sleep(1)  # 模拟加载时间
            
            # 解析配置文件获取类别和调色板信息
            try:
                from config_parser import parse_mmseg_config
                config_info = parse_mmseg_config(config_path)
            except Exception as parse_error:
                # 配置解析失败不应该导致模型加载失败
                self._log_to_bottom(f"⚠️  配置解析警告: {parse_error}")
                config_info = {
                    'classes': None,
                    'palette': None,
                    'model_name': None
                }
            
            # 保存模型信息
            self.inference_model = {
                'config': config_path,
                'checkpoint': checkpoint_path,
                'device': device,
                'classes': config_info.get('classes'),
                'palette': config_info.get('palette')
            }  # 占位符，实际应该是真实的模型对象
            
            # 更新 UI 状态 - 加载成功
            self.ui.pushButton_loadModel.setEnabled(True)
            self.ui.label_modelStatus.setText("模型已就绪")
            self.ui.label_modelStatus.setStyleSheet("color: #28a745; font-weight: bold;")
            
            # 显示类别图例（即使为空也不会失败）
            try:
                self._display_classes_legend(config_info.get('classes'), config_info.get('palette'))
            except Exception as legend_error:
                self._log_to_bottom(f"⚠️  类别图例显示警告: {legend_error}")
            
            # 底部日志显示
            self._log_to_bottom("✅ 模型已就绪 (Model Ready)")
            
        except Exception as e:
            # 更新 UI 状态 - 加载失败
            self.ui.pushButton_loadModel.setEnabled(True)
            self.ui.label_modelStatus.setText("加载失败")
            self.ui.label_modelStatus.setStyleSheet("color: #dc3545; font-weight: bold;")
            
            # 底部日志显示 - 添加详细的错误信息
            import traceback
            error_details = traceback.format_exc()
            self._log_to_bottom(f"❌ 模型加载失败: {e}")
            self._log_to_bottom(f"详细错误:\n{error_details}")
            
            QMessageBox.critical(self, "模型加载失败", f"模型加载过程中发生错误。\n\n错误信息:\n{str(e)}\n\n详细信息请查看日志面板。")
    
    def _display_classes_legend(self, classes, palette):
        """显示类别图例"""
        try:
            # 清空之前的内容
            layout = self.ui.verticalLayout_classes
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # 安全检查：确保 classes 和 palette 不是 None
            if classes is None:
                classes = []
            if palette is None:
                palette = []
            
            if not classes or not palette:
                # 如果没有类别信息，隐藏图例区域
                self.ui.scrollArea_classesLegend.setVisible(False)
                self._log_to_bottom("⚠️  配置文件中未找到 CLASSES 或 PALETTE 信息")
                return
            
            # 显示图例区域
            self.ui.scrollArea_classesLegend.setVisible(True)
            
            # 为每个类别创建一个标签
            for idx, class_name in enumerate(classes):
                try:
                    # 获取对应的颜色
                    if idx < len(palette):
                        color = palette[idx]
                        # 确保颜色是有效的三元组
                        if isinstance(color, (list, tuple)) and len(color) >= 3:
                            r, g, b = int(color[0]), int(color[1]), int(color[2])
                        else:
                            r, g, b = 128, 128, 128  # 默认灰色
                    else:
                        # 如果调色板不够，使用默认颜色
                        r, g, b = 128, 128, 128
                    
                    # 创建类别标签
                    class_label = QLabel(self.ui.scrollAreaWidgetContents_classes)
                    class_label.setObjectName(f"label_class_{idx}")
                    
                    # 设置样式：颜色块 + 类别名称
                    class_label.setText(f"  {str(class_name)}")
                    class_label.setStyleSheet(
                        f"background-color: rgb({r}, {g}, {b}); "
                        f"color: {'white' if (r + g + b) < 384 else 'black'}; "
                        f"padding: 3px 8px; "
                        f"border-radius: 3px; "
                        f"font-size: 11px;"
                    )
                    
                    layout.addWidget(class_label)
                except Exception as label_error:
                    # 单个标签创建失败不应该影响整个过程
                    self._log_to_bottom(f"⚠️  创建类别标签 {idx} 失败: {label_error}")
                    continue
            
            # 添加弹性空间
            layout.addStretch()
            
            # 日志输出
            if classes:
                self._log_to_bottom(f"📊 已加载 {len(classes)} 个类别")
            
        except Exception as e:
            # 整个方法失败也不应该影响模型加载
            self._log_to_bottom(f"⚠️  类别图例显示失败: {e}")
            # 隐藏图例区域
            try:
                self.ui.scrollArea_classesLegend.setVisible(False)
            except:
                pass
    
    def _log_to_bottom(self, message: str):
        """输出日志到底部日志面板"""
        # 获取当前时间
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 格式化日志消息
        log_message = f"[{timestamp}] {message}"
        
        # 输出到控制台
        print(log_message)
        
        # 输出到底部日志 TextEdit
        self.ui.textEdit_logs.append(log_message)
        
        # 滚动到底部
        scrollbar = self.ui.textEdit_logs.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
