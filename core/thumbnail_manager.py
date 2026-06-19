# -*- coding: utf-8 -*-
"""
缩略图懒加载管理器 (Thumbnail Lazy Loading Manager)
只加载可见区域的缩略图，使用 QThreadPool 管理任务
"""

from PySide6.QtWidgets import QListWidget
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject, QTimer, QMutex, QMutexLocker
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QColor
import os
import hashlib
from skills.skill_image_processing import VOC_PALETTE, apply_colormap as _apply_colormap_func, apply_linear_stretch as _apply_linear_stretch_func


class ThumbnailSignals(QObject):
    """缩略图加载信号"""
    ready = Signal(str, QPixmap, QPixmap)  # (key, image_pixmap, label_pixmap)
    error = Signal(str, str)  # (key, error_msg)


class ThumbnailTask(QRunnable):
    """单个缩略图加载任务"""
    
    def __init__(self, key, image_path, label_path, thumbnail_size=120):
        super().__init__()
        self.key = key
        self.image_path = image_path
        self.label_path = label_path
        self.thumbnail_size = thumbnail_size
        self.signals = ThumbnailSignals()
        self._is_cancelled = False
    
    def cancel(self):
        """标记任务为取消"""
        self._is_cancelled = True
    
    def _apply_colormap(self, label_image):
        """将标签图像转换为伪彩色（委托给 skill_image_processing）"""
        return _apply_colormap_func(label_image, VOC_PALETTE)
    
    def _apply_linear_stretch(self, image, percent=2):
        """对图像应用线性拉伸（委托给 skill_image_processing）"""
        return _apply_linear_stretch_func(image, percent)
    
    def run(self):
        """执行缩略图加载"""
        if self._is_cancelled:
            return
        
        image_pixmap = QPixmap()
        label_pixmap = QPixmap()
        
        try:
            # 加载原图
            if self.image_path and os.path.exists(self.image_path):
                image = QImage(self.image_path)
                if not image.isNull():
                    # 先缩放
                    scaled = image.scaled(
                        self.thumbnail_size, self.thumbnail_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    # 再拉伸
                    stretched = self._apply_linear_stretch(scaled, percent=2)
                    image_pixmap = QPixmap.fromImage(stretched)
            
            if self._is_cancelled:
                return
            
            # 加载标签
            if self.label_path and os.path.exists(self.label_path):
                label_image = QImage(self.label_path)
                if not label_image.isNull():
                    colored = self._apply_colormap(label_image)
                    scaled = colored.scaled(
                        self.thumbnail_size, self.thumbnail_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    label_pixmap = QPixmap.fromImage(scaled)
            
            if not self._is_cancelled:
                self.signals.ready.emit(self.key, image_pixmap, label_pixmap)
        
        except Exception as e:
            if not self._is_cancelled:
                self.signals.error.emit(self.key, str(e))


class ThumbnailLazyLoader:
    """缩略图懒加载管理器"""
    
    def __init__(self, list_widget, thumbnail_size=120):
        """
        Args:
            list_widget: QListWidget 实例
            thumbnail_size: 缩略图尺寸
        """
        self.list_widget = list_widget
        self.thumbnail_size = thumbnail_size
        
        # 线程池
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)  # 限制并发数
        
        # 样本数据 {key: {'image_path': str, 'label_path': str, 'item': QListWidgetItem}}
        self.samples = {}
        
        # 已加载的缩略图数据 {key: {'image': QPixmap, 'label': QPixmap}}
        self.loaded_data = {}
        
        # 合成缓存 {cache_key: QPixmap}
        self.composite_cache = {}
        
        # 当前图层设置
        self.show_image = True
        self.show_label = True
        self.opacity = 70
        
        # 待处理任务 {key: ThumbnailTask}
        self.pending_tasks = {}
        self.task_mutex = QMutex()
        
        # 防抖定时器
        self._scroll_timer = QTimer()
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(100)  # 100ms 防抖
        self._scroll_timer.timeout.connect(self._load_visible_thumbnails)
        
        # 连接滚动信号
        scrollbar = self.list_widget.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_scroll)
        
        # 连接resize信号
        self.list_widget.resizeEvent = self._on_resize
        
        # 占位图
        self._placeholder = self._create_placeholder()
        
        # Phase 1.4: 磁盘缓存目录
        self._cache_dir = None
    
    def _create_placeholder(self):
        """创建占位图"""
        pixmap = QPixmap(self.thumbnail_size, self.thumbnail_size)
        pixmap.fill(QColor(128, 128, 128, 50))
        return QIcon(pixmap)
    
    def clear(self):
        """清空所有数据"""
        # 取消所有待处理任务
        with QMutexLocker(self.task_mutex):
            for task in self.pending_tasks.values():
                task.cancel()
            self.pending_tasks.clear()
        
        self.samples.clear()
        self.loaded_data.clear()
        self.composite_cache.clear()
        self.list_widget.clear()
    
    def add_sample(self, key, sample_id, dataset_type, image_path, label_path):
        """添加样本（只创建占位项，不加载缩略图）"""
        from PySide6.QtWidgets import QListWidgetItem
        
        item = QListWidgetItem()
        item.setText(sample_id)
        item.setIcon(self._placeholder)
        item.setData(Qt.ItemDataRole.UserRole, {
            'sample_id': sample_id,
            'dataset': dataset_type
        })
        
        self.list_widget.addItem(item)
        
        self.samples[key] = {
            'sample_id': sample_id,
            'dataset': dataset_type,
            'image_path': image_path,
            'label_path': label_path,
            'item': item
        }
    
    def _on_scroll(self, value):
        """滚动事件（防抖）"""
        self._scroll_timer.start()
    
    def _on_resize(self, event):
        """窗口大小改变事件"""
        # 调用原始的resizeEvent
        from PySide6.QtWidgets import QListWidget
        QListWidget.resizeEvent(self.list_widget, event)
        # 触发重新加载可见区域
        self._scroll_timer.start()
    
    def _get_visible_items(self):
        """获取当前可见区域的项"""
        visible_keys = []
        viewport = self.list_widget.viewport()
        viewport_rect = viewport.rect()
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_rect = self.list_widget.visualItemRect(item)
            
            # 检查是否在可见区域内（包含部分可见）
            if item_rect.intersects(viewport_rect):
                # 查找对应的key
                for key, data in self.samples.items():
                    if data['item'] is item:
                        visible_keys.append(key)
                        break
        
        return visible_keys
    
    def _load_visible_thumbnails(self):
        """加载可见区域的缩略图"""
        visible_keys = self._get_visible_items()
        
        # 取消不在可见区域的待处理任务
        with QMutexLocker(self.task_mutex):
            keys_to_cancel = [k for k in self.pending_tasks.keys() if k not in visible_keys]
            for key in keys_to_cancel:
                self.pending_tasks[key].cancel()
                del self.pending_tasks[key]
        
        # 加载可见区域中未加载的缩略图
        for key in visible_keys:
            if key in self.loaded_data:
                # 已加载，直接更新显示
                self._update_item_display(key)
            elif key not in self.pending_tasks:
                # 未加载且未在队列中，创建任务
                self._start_load_task(key)
    
    def _start_load_task(self, key):
        """启动加载任务"""
        if key not in self.samples:
            return
        
        # Phase 1.4: 尝试从磁盘缓存加载
        if self._try_load_from_disk_cache(key):
            return
        
        sample = self.samples[key]
        task = ThumbnailTask(
            key,
            sample['image_path'],
            sample['label_path'],
            self.thumbnail_size
        )
        task.signals.ready.connect(self._on_thumbnail_ready)
        task.signals.error.connect(self._on_thumbnail_error)
        
        with QMutexLocker(self.task_mutex):
            self.pending_tasks[key] = task
        
        self.thread_pool.start(task)
    
    def _on_thumbnail_ready(self, key, image_pixmap, label_pixmap):
        """缩略图加载完成"""
        # 从待处理列表移除
        with QMutexLocker(self.task_mutex):
            if key in self.pending_tasks:
                del self.pending_tasks[key]
        
        # 保存数据
        self.loaded_data[key] = {
            'image': image_pixmap,
            'label': label_pixmap
        }
        
        # 更新显示
        self._update_item_display(key)
    
    def _on_thumbnail_error(self, key, error_msg):
        """缩略图加载错误"""
        with QMutexLocker(self.task_mutex):
            if key in self.pending_tasks:
                del self.pending_tasks[key]
        print(f"⚠️ Thumbnail load failed [{key}]: {error_msg}")
    
    def _update_item_display(self, key):
        """更新单个项的显示"""
        if key not in self.samples or key not in self.loaded_data:
            return
        
        item = self.samples[key]['item']
        data = self.loaded_data[key]
        image_pixmap = data['image']
        label_pixmap = data['label']
        
        # 生成缓存键
        cache_key = f"{key}_{self.show_image}_{self.show_label}_{self.opacity}"
        
        # 检查缓存
        if cache_key in self.composite_cache:
            item.setIcon(QIcon(self.composite_cache[cache_key]))
            return
        
        # 合成图像
        if image_pixmap.isNull() and label_pixmap.isNull():
            return
        
        if not image_pixmap.isNull():
            result = QPixmap(image_pixmap.size())
        else:
            result = QPixmap(label_pixmap.size())
        result.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        
        if self.show_image and not image_pixmap.isNull():
            painter.drawPixmap(0, 0, image_pixmap)
        
        if self.show_label and not label_pixmap.isNull():
            painter.setOpacity(self.opacity / 100.0)
            painter.drawPixmap(0, 0, label_pixmap)
        
        painter.end()
        
        # 缓存并显示
        self.composite_cache[cache_key] = result
        item.setIcon(QIcon(result))
        
        # Phase 1.4: 保存到磁盘缓存
        self._save_composite_to_disk(key, result)
    
    def set_layer_settings(self, show_image, show_label, opacity):
        """设置图层参数"""
        if (self.show_image == show_image and 
            self.show_label == show_label and 
            self.opacity == opacity):
            return
        
        self.show_image = show_image
        self.show_label = show_label
        self.opacity = opacity
        
        # 清空合成缓存
        self.composite_cache.clear()
        
        # 刷新已加载的可见项
        visible_keys = self._get_visible_items()
        for key in visible_keys:
            if key in self.loaded_data:
                self._update_item_display(key)
    
    def refresh_visible(self):
        """刷新可见区域"""
        self._load_visible_thumbnails()
    
    def trigger_initial_load(self):
        """触发初始加载（切换到网格视图时调用）"""
        # 延迟一点执行，确保布局完成
        QTimer.singleShot(50, self._load_visible_thumbnails)
    
    # ==================== Phase 1.4: 磁盘缓存 ====================
    
    def set_cache_dir(self, data_root):
        """
        设置磁盘缓存目录。
        会在 data_root 下创建 .cache/thumbnails/ 目录。
        
        Args:
            data_root: Dataset Root Dir。
        """
        if not data_root:
            self._cache_dir = None
            return
        
        cache_dir = os.path.join(data_root, '.cache', 'thumbnails')
        try:
            os.makedirs(cache_dir, exist_ok=True)
            self._cache_dir = cache_dir
            print(f'📁 Thumbnail cache dir: {cache_dir}')
        except OSError as e:
            print(f'⚠️ Cannot create cache directory: {e}')
            self._cache_dir = None
    
    def _get_cache_path(self, key):
        """根据 key 生成磁盘缓存文件路径"""
        if not self._cache_dir:
            return None
        # 用 key 的 hash 作为文件名，避免特殊字符问题
        safe_name = hashlib.md5(key.encode('utf-8')).hexdigest()
        return os.path.join(self._cache_dir, f'thumb_{safe_name}.jpg')
    
    def _try_load_from_disk_cache(self, key):
        """
        尝试从磁盘缓存加载缩略图。
        如果缓存命中，直接设置到 QListWidgetItem 并返回 True。
        """
        cache_path = self._get_cache_path(key)
        if not cache_path or not os.path.exists(cache_path):
            return False
        
        pixmap = QPixmap(cache_path)
        if pixmap.isNull():
            return False
        
        # 将磁盘缓存视为 "image" 层，无 label 层（因为磁盘缓存已是合成后的结果）
        self.loaded_data[key] = {
            'image': pixmap,
            'label': QPixmap()  # 空的
        }
        
        # 直接设置图标（缓存已是合成后的，无需再走 composite 流程）
        if key in self.samples:
            self.samples[key]['item'].setIcon(QIcon(pixmap))
        
        return True
    
    def _save_composite_to_disk(self, key, composite_pixmap):
        """将合成后的缩略图保存到磁盘缓存"""
        cache_path = self._get_cache_path(key)
        if not cache_path or composite_pixmap.isNull():
            return
        
        try:
            composite_pixmap.save(cache_path, 'JPEG', 85)
        except Exception as e:
            print(f'⚠️ Save thumbnail cache failed [{key}]: {e}')
