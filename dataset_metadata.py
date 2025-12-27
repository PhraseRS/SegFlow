# -*- coding: utf-8 -*-
"""
数据集元数据缓存系统 (Dataset Metadata Cache)
使用独立进程计算统计信息，SQLite 数据库存储
"""

import sqlite3
import os
import json
import multiprocessing
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Signal, QObject


# ============== 独立进程中运行的计算函数 ==============

def _calculate_sample_stats(args):
    """
    计算单个样本的统计信息（在独立进程中运行）
    
    Args:
        args: (sample_id, dataset_type, label_path)
    
    Returns:
        dict: 样本统计信息，包含：
            - class_pixels: 各类别像素数
            - classes_present: 该样本中出现的类别列表（用于统计 image_counts）
    """
    sample_id, dataset_type, label_path = args
    
    stats = {
        'sample_id': sample_id,
        'dataset': dataset_type,
        'label_path': label_path,
        'width': 0,
        'height': 0,
        'total_pixels': 0,
        'class_pixels': {},
        'classes_present': [],  # 该样本中出现的类别列表
        'error': None
    }
    
    if not label_path or not os.path.exists(label_path):
        return stats
    
    try:
        # 使用 PIL 读取图像（在独立进程中不能使用 Qt）
        from PIL import Image
        import numpy as np
        
        with Image.open(label_path) as img:
            # 转换为灰度/单通道
            if img.mode != 'L':
                img = img.convert('L')
            
            arr = np.array(img)
            stats['height'], stats['width'] = arr.shape
            stats['total_pixels'] = arr.size
            
            # 统计各类别像素数
            unique, counts = np.unique(arr, return_counts=True)
            stats['class_pixels'] = {str(int(k)): int(v) for k, v in zip(unique, counts)}
            
            # 记录该样本中出现的类别（用于统计 image_counts）
            stats['classes_present'] = [str(int(k)) for k in unique]
    
    except Exception as e:
        stats['error'] = str(e)
    
    return stats


def _worker_process(db_path, samples_queue, progress_queue, stop_event, total_samples):
    """
    工作进程：从队列获取任务，计算统计信息，写入数据库
    
    Args:
        db_path: SQLite 数据库路径
        samples_queue: 样本任务队列
        progress_queue: 进度报告队列
        stop_event: 停止事件
        total_samples: 总样本数（用于计算进度报告间隔）
    """
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    processed = 0
    last_report = 0
    
    # 计算报告间隔：每处理 1% 或至少 50 个样本报告一次，最少间隔 100 个
    report_interval = max(50, min(100, total_samples // 100))
    
    while not stop_event.is_set():
        try:
            # 非阻塞获取任务
            try:
                args = samples_queue.get(timeout=0.1)
            except:
                continue
            
            if args is None:  # 结束信号
                break
            
            # 计算统计信息
            stats = _calculate_sample_stats(args)
            
            # 写入数据库
            cursor.execute('''
                INSERT OR REPLACE INTO sample_stats 
                (sample_id, dataset, label_path, width, height, total_pixels, class_pixels, classes_present, error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                stats['sample_id'],
                stats['dataset'],
                stats['label_path'],
                stats['width'],
                stats['height'],
                stats['total_pixels'],
                json.dumps(stats['class_pixels']),
                json.dumps(stats.get('classes_present', [])),
                stats['error'],
                datetime.now().isoformat()
            ))
            conn.commit()
            
            processed += 1
            
            # 降频报告进度：每 report_interval 个样本报告一次
            if processed - last_report >= report_interval:
                last_report = processed
                progress_queue.put({
                    'type': 'progress',
                    'sample_id': stats['sample_id'],
                    'processed': processed
                })
        
        except Exception as e:
            progress_queue.put({
                'type': 'error',
                'message': str(e)
            })
    
    conn.close()
    progress_queue.put({'type': 'done', 'processed': processed})


# ============== 数据库管理类 ==============

class MetadataDatabase:
    """元数据 SQLite 数据库管理"""
    
    DB_FILENAME = '.dataset_metadata.db'
    
    def __init__(self, data_root):
        self.data_root = data_root
        self.db_path = os.path.join(data_root, self.DB_FILENAME)
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 样本统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sample_stats (
                sample_id TEXT PRIMARY KEY,
                dataset TEXT,
                label_path TEXT,
                width INTEGER,
                height INTEGER,
                total_pixels INTEGER,
                class_pixels TEXT,
                classes_present TEXT,
                error TEXT,
                updated_at TEXT
            )
        ''')
        
        # 检查是否需要添加 classes_present 列（兼容旧数据库）
        cursor.execute("PRAGMA table_info(sample_stats)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'classes_present' not in columns:
            cursor.execute('ALTER TABLE sample_stats ADD COLUMN classes_present TEXT')
            print("📦 数据库升级：添加 classes_present 列")
        
        # 元数据信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_sample_count(self):
        """获取已统计的样本数量"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sample_stats')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_sample_ids(self):
        """获取所有已统计的样本ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT sample_id FROM sample_stats')
        ids = set(row[0] for row in cursor.fetchall())
        conn.close()
        return ids
    
    def get_aggregated_stats(self):
        """
        获取聚合统计数据（直接从数据库读取，毫秒级）
        
        Returns:
            dict: 聚合统计信息，包含：
                - class_distribution: 各类别像素总数
                - image_counts: 各类别出现在多少张图像中
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            'total_samples': 0,
            'train_count': 0,
            'val_count': 0,
            'test_count': 0,
            'class_distribution': {},
            'image_counts': {},  # 各类别出现在多少张图像中
            'size_stats': {
                'min_width': float('inf'),
                'min_height': float('inf'),
                'max_width': 0,
                'max_height': 0,
                'widths': [],
                'heights': []
            }
        }
        
        # 统计各数据集样本数
        cursor.execute('SELECT dataset, COUNT(*) FROM sample_stats GROUP BY dataset')
        for dataset, count in cursor.fetchall():
            stats['total_samples'] += count
            if dataset == 'train':
                stats['train_count'] = count
            elif dataset == 'val':
                stats['val_count'] = count
            elif dataset == 'test':
                stats['test_count'] = count
        
        # 聚合类别分布（像素计数）和图像计数
        cursor.execute('SELECT class_pixels, classes_present FROM sample_stats WHERE class_pixels IS NOT NULL')
        for row in cursor.fetchall():
            try:
                # 聚合像素计数
                class_pixels = json.loads(row[0])
                for class_id, count in class_pixels.items():
                    stats['class_distribution'][class_id] = \
                        stats['class_distribution'].get(class_id, 0) + count
                
                # 聚合图像计数：每个样本中出现的类别，该类别的 image_count +1
                classes_present = json.loads(row[1]) if row[1] else list(class_pixels.keys())
                for class_id in classes_present:
                    stats['image_counts'][class_id] = \
                        stats['image_counts'].get(class_id, 0) + 1
            except:
                pass
        
        # 统计尺寸
        cursor.execute('SELECT width, height FROM sample_stats WHERE width > 0 AND height > 0')
        for width, height in cursor.fetchall():
            stats['size_stats']['widths'].append(width)
            stats['size_stats']['heights'].append(height)
            stats['size_stats']['min_width'] = min(stats['size_stats']['min_width'], width)
            stats['size_stats']['min_height'] = min(stats['size_stats']['min_height'], height)
            stats['size_stats']['max_width'] = max(stats['size_stats']['max_width'], width)
            stats['size_stats']['max_height'] = max(stats['size_stats']['max_height'], height)
        
        conn.close()
        
        # 处理空数据情况
        if stats['size_stats']['min_width'] == float('inf'):
            stats['size_stats']['min_width'] = 0
            stats['size_stats']['min_height'] = 0
        
        return stats
    
    def clear(self):
        """清空数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sample_stats')
        conn.commit()
        conn.close()


# ============== 元数据管理器（Qt 集成）==============

class MetadataSignals(QObject):
    """元数据计算信号"""
    progress = Signal(int, int, str)  # (current, total, sample_id)
    finished = Signal()
    error = Signal(str)


class DatasetMetadataManager:
    """数据集元数据管理器（使用独立进程计算）"""
    
    def __init__(self):
        self.database = None
        self.data_root = None
        
        # 进程相关
        self._process = None
        self._samples_queue = None
        self._progress_queue = None
        self._stop_event = None
        self._total_samples = 0
        
        # Qt 信号
        self.signals = MetadataSignals()
        
        # 进度轮询定时器
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)  # 100ms 轮询
        self._poll_timer.timeout.connect(self._poll_progress)
    
    def init_database(self, data_root):
        """初始化数据库"""
        self.data_root = data_root
        self.database = MetadataDatabase(data_root)
    
    def is_cache_valid(self, samples_info):
        """
        检查缓存是否有效
        
        Args:
            samples_info: [(sample_id, dataset_type), ...]
        
        Returns:
            bool: 缓存是否有效
        """
        if self.database is None:
            return False
        
        cached_ids = self.database.get_sample_ids()
        current_ids = set(s[0] for s in samples_info)
        
        return cached_ids == current_ids
    
    def get_aggregated_stats(self):
        """获取聚合统计数据（从数据库读取）"""
        if self.database is None:
            return None
        return self.database.get_aggregated_stats()
    
    def start_calculation(self, samples_info, labels_dir):
        """
        启动后台进程计算元数据
        
        Args:
            samples_info: [(sample_id, dataset_type), ...]
            labels_dir: 标签目录
        """
        # 停止之前的计算
        self.stop_calculation()
        
        if self.database is None:
            return
        
        # 检查哪些样本需要计算
        cached_ids = self.database.get_sample_ids()
        samples_to_process = []
        
        label_exts = ['.png', '.tif', '.tiff', '.jpg', '.jpeg', '.bmp']
        
        for sample_id, dataset_type in samples_info:
            if sample_id in cached_ids:
                continue  # 已缓存，跳过
            
            # 查找标签文件
            label_path = None
            for ext in label_exts:
                path = os.path.join(labels_dir, f"{sample_id}{ext}")
                if os.path.exists(path):
                    label_path = path
                    break
            
            samples_to_process.append((sample_id, dataset_type, label_path))
        
        if not samples_to_process:
            print("✅ 所有样本已缓存，无需计算")
            self.signals.finished.emit()
            return
        
        self._total_samples = len(samples_to_process)
        print(f"🔄 启动后台进程计算 {self._total_samples} 个样本的元数据...")
        
        # 创建进程间通信对象
        self._samples_queue = multiprocessing.Queue()
        self._progress_queue = multiprocessing.Queue()
        self._stop_event = multiprocessing.Event()
        
        # 将任务放入队列
        for args in samples_to_process:
            self._samples_queue.put(args)
        self._samples_queue.put(None)  # 结束信号
        
        # 启动工作进程
        self._process = multiprocessing.Process(
            target=_worker_process,
            args=(self.database.db_path, self._samples_queue, self._progress_queue, 
                  self._stop_event, self._total_samples)
        )
        self._process.start()
        
        # 启动进度轮询
        self._poll_timer.start()
    
    def _poll_progress(self):
        """轮询进度队列"""
        while True:
            try:
                msg = self._progress_queue.get_nowait()
            except:
                break
            
            if msg['type'] == 'progress':
                self.signals.progress.emit(
                    msg['processed'], 
                    self._total_samples, 
                    msg['sample_id']
                )
            elif msg['type'] == 'done':
                self._poll_timer.stop()
                self._cleanup_process()
                print(f"✅ 元数据计算完成，共处理 {msg['processed']} 个样本")
                self.signals.finished.emit()
                break
            elif msg['type'] == 'error':
                print(f"⚠️ 元数据计算错误: {msg['message']}")
                self.signals.error.emit(msg['message'])
    
    def stop_calculation(self):
        """停止计算"""
        if self._stop_event:
            self._stop_event.set()
        self._poll_timer.stop()
        self._cleanup_process()
    
    def _cleanup_process(self):
        """清理进程资源"""
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1)
        self._process = None
        self._samples_queue = None
        self._progress_queue = None
        self._stop_event = None
