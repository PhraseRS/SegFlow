# -*- coding: utf-8 -*-
"""
数据集元数据缓存系统 (Dataset Metadata Cache)
使用独立进程计算统计信息，SQLite 数据库存储

全能分析流水线：一次 I/O，完成统计 + 质检
- 类别分布统计
- 覆盖率分析
- 健康检查（文件缺失、损坏、尺寸不匹配、空标签、噪点等）
"""

import sqlite3
import os
import json
import multiprocessing
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Signal, QObject

# --- 从 skill_sample_analysis 导入可复用的质检逻辑 ---
from skills.skill_sample_analysis import (
    ISSUE_FILE_MISSING, ISSUE_CORRUPT_FILE, ISSUE_DIMENSION_MISMATCH,
    ISSUE_CHANNEL_MISMATCH, ISSUE_INVALID_CLASS_ID, ISSUE_DTYPE_MISMATCH,
    ISSUE_EMPTY_MASK, ISSUE_NOISE_ARTIFACT, ISSUE_HIGH_NODATA_COVERAGE,
    LEVEL_FATAL, LEVEL_WARNING, ISSUE_LEVELS,
    NOISE_AREA_THRESHOLD, NODATA_COVERAGE_THRESHOLD, VALID_CLASS_IDS,
    analyze_sample_fully as _analyze_sample_fully_impl,
)


# ============== 独立进程中运行的计算函数 ==============

def _analyze_sample_fully(args):
    """全能分析函数（委托给 skill_sample_analysis）"""
    return _analyze_sample_fully_impl(args)


def _worker_process(db_path, samples_queue, progress_queue, stop_event, total_samples):
    """
    工作进程：从队列获取任务，执行全能分析，写入数据库
    
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
            
            # 执行全能分析
            result = _analyze_sample_fully(args)
            
            # 提取统计数据
            stats = result.get('stats') or {}
            
            # 写入数据库
            cursor.execute('''
                INSERT OR REPLACE INTO sample_stats 
                (sample_id, dataset, image_path, label_path, width, height, total_pixels, 
                 class_pixels, class_ratios, classes_present, status, issues, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result['sample_id'],
                result['dataset'],
                result.get('image_path', ''),
                result.get('label_path', ''),
                stats.get('width', 0),
                stats.get('height', 0),
                stats.get('total_pixels', 0),
                json.dumps(stats.get('class_pixels', {})),
                json.dumps(stats.get('class_ratios', {})),
                json.dumps(stats.get('classes_present', [])),
                result['status'],
                json.dumps(result['issues']),
                datetime.now().isoformat()
            ))
            conn.commit()
            
            processed += 1
            
            # 降频报告进度：每 report_interval 个样本报告一次
            if processed - last_report >= report_interval:
                last_report = processed
                progress_queue.put({
                    'type': 'progress',
                    'sample_id': result['sample_id'],
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
        
        # 样本统计表（包含健康检查字段）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sample_stats (
                sample_id TEXT PRIMARY KEY,
                dataset TEXT,
                image_path TEXT,
                label_path TEXT,
                width INTEGER,
                height INTEGER,
                total_pixels INTEGER,
                class_pixels TEXT,
                class_ratios TEXT,
                classes_present TEXT,
                status TEXT DEFAULT 'ok',
                issues TEXT DEFAULT '[]',
                error TEXT,
                updated_at TEXT
            )
        ''')
        
        # 检查是否需要添加新列（兼容旧数据库）
        cursor.execute("PRAGMA table_info(sample_stats)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'classes_present' not in columns:
            cursor.execute('ALTER TABLE sample_stats ADD COLUMN classes_present TEXT')
            print("📦 数据库升级：添加 classes_present 列")
        
        if 'class_ratios' not in columns:
            cursor.execute('ALTER TABLE sample_stats ADD COLUMN class_ratios TEXT')
            print("📦 数据库升级：添加 class_ratios 列")
        
        if 'status' not in columns:
            cursor.execute("ALTER TABLE sample_stats ADD COLUMN status TEXT DEFAULT 'ok'")
            print("📦 数据库升级：添加 status 列")
        
        if 'issues' not in columns:
            cursor.execute("ALTER TABLE sample_stats ADD COLUMN issues TEXT DEFAULT '[]'")
            print("📦 数据库升级：添加 issues 列")
        
        if 'image_path' not in columns:
            cursor.execute('ALTER TABLE sample_stats ADD COLUMN image_path TEXT')
            print("📦 数据库升级：添加 image_path 列")
        
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
        仅统计 status != 'error' 的样本
        
        Returns:
            dict: 聚合统计信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            'total_samples': 0,
            'train_count': 0,
            'val_count': 0,
            'test_count': 0,
            'class_distribution': {},
            'image_counts': {},
            'size_stats': {
                'min_width': float('inf'),
                'min_height': float('inf'),
                'max_width': 0,
                'max_height': 0,
                'widths': [],
                'heights': []
            }
        }
        
        # 统计各数据集样本数（仅统计非错误样本）
        cursor.execute('''
            SELECT dataset, COUNT(*) FROM sample_stats 
            WHERE status != 'error' OR status IS NULL
            GROUP BY dataset
        ''')
        for dataset, count in cursor.fetchall():
            stats['total_samples'] += count
            if dataset == 'train':
                stats['train_count'] = count
            elif dataset == 'val':
                stats['val_count'] = count
            elif dataset == 'test':
                stats['test_count'] = count
        
        # 聚合类别分布（仅统计非错误样本）
        cursor.execute('''
            SELECT class_pixels, classes_present FROM sample_stats 
            WHERE class_pixels IS NOT NULL AND (status != 'error' OR status IS NULL)
        ''')
        for row in cursor.fetchall():
            try:
                class_pixels = json.loads(row[0])
                for class_id, count in class_pixels.items():
                    stats['class_distribution'][class_id] = \
                        stats['class_distribution'].get(class_id, 0) + count
                
                classes_present = json.loads(row[1]) if row[1] else list(class_pixels.keys())
                for class_id in classes_present:
                    stats['image_counts'][class_id] = \
                        stats['image_counts'].get(class_id, 0) + 1
            except:
                pass
        
        # 统计尺寸
        cursor.execute('''
            SELECT width, height FROM sample_stats 
            WHERE width > 0 AND height > 0 AND (status != 'error' OR status IS NULL)
        ''')
        for width, height in cursor.fetchall():
            stats['size_stats']['widths'].append(width)
            stats['size_stats']['heights'].append(height)
            stats['size_stats']['min_width'] = min(stats['size_stats']['min_width'], width)
            stats['size_stats']['min_height'] = min(stats['size_stats']['min_height'], height)
            stats['size_stats']['max_width'] = max(stats['size_stats']['max_width'], width)
            stats['size_stats']['max_height'] = max(stats['size_stats']['max_height'], height)
        
        conn.close()
        
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

    
    def get_image_records(self, dataset_filter=None):
        """
        获取单图记录列表（用于覆盖率分析）
        仅返回 status != 'error' 的样本
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if dataset_filter:
            cursor.execute('''
                SELECT sample_id, dataset, total_pixels, class_ratios, class_pixels, width, height 
                FROM sample_stats 
                WHERE dataset = ? AND (class_ratios IS NOT NULL OR class_pixels IS NOT NULL)
                AND (status != 'error' OR status IS NULL)
            ''', (dataset_filter,))
        else:
            cursor.execute('''
                SELECT sample_id, dataset, total_pixels, class_ratios, class_pixels, width, height 
                FROM sample_stats 
                WHERE (class_ratios IS NOT NULL OR class_pixels IS NOT NULL)
                AND (status != 'error' OR status IS NULL)
            ''')
        
        records = []
        for row in cursor.fetchall():
            try:
                sample_id = row[0]
                dataset = row[1]
                total_pixels = row[2] or 0
                class_ratios_str = row[3]
                class_pixels_str = row[4]
                width = row[5]
                height = row[6]
                
                class_ratios = {}
                if class_ratios_str:
                    class_ratios = json.loads(class_ratios_str)
                
                if not class_ratios and class_pixels_str and total_pixels > 0:
                    class_pixels = json.loads(class_pixels_str)
                    for class_id, pixel_count in class_pixels.items():
                        ratio = pixel_count / total_pixels
                        if ratio > 0:
                            class_ratios[class_id] = ratio
                
                if class_ratios:
                    records.append({
                        'sample_id': sample_id,
                        'dataset': dataset,
                        'total_pixels': total_pixels,
                        'class_ratios': class_ratios,
                        'width': width,
                        'height': height
                    })
            except:
                pass
        
        conn.close()
        return records
    
    def get_samples_by_class(self, class_id, min_ratio=0.0):
        """获取包含指定类别的样本列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sample_id, dataset, total_pixels, class_ratios, class_pixels, width, height 
            FROM sample_stats 
            WHERE (class_ratios IS NOT NULL OR class_pixels IS NOT NULL)
            AND (status != 'error' OR status IS NULL)
        ''')
        
        records = []
        for row in cursor.fetchall():
            try:
                sample_id = row[0]
                dataset = row[1]
                total_pixels = row[2] or 0
                class_ratios_str = row[3]
                class_pixels_str = row[4]
                width = row[5]
                height = row[6]
                
                class_ratios = {}
                if class_ratios_str:
                    class_ratios = json.loads(class_ratios_str)
                
                if not class_ratios and class_pixels_str and total_pixels > 0:
                    class_pixels = json.loads(class_pixels_str)
                    for cid, pixel_count in class_pixels.items():
                        ratio = pixel_count / total_pixels
                        if ratio > 0:
                            class_ratios[cid] = ratio
                
                if class_id in class_ratios and class_ratios[class_id] >= min_ratio:
                    records.append({
                        'sample_id': sample_id,
                        'dataset': dataset,
                        'total_pixels': total_pixels,
                        'class_ratios': class_ratios,
                        'ratio': class_ratios[class_id],
                        'width': width,
                        'height': height
                    })
            except:
                pass
        
        conn.close()
        records.sort(key=lambda x: x['ratio'], reverse=True)
        return records
    
    def get_health_check_issues(self):
        """
        获取健康检查问题汇总（用于健康检查卡片）
        
        Returns:
            dict: 问题汇总，格式：
                {
                    'fatal': {'file_missing': ['file1', ...], 'corrupt_file': [...], ...},
                    'warning': {'empty_mask': [...], 'noise_artifact': [...], ...},
                    'total_samples': 总样本数,
                    'passed_samples': 通过样本数
                }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 初始化结果
        result = {
            'fatal': {},
            'warning': {},
            'total_samples': 0,
            'passed_samples': 0
        }
        
        # 查询所有样本的状态和问题
        cursor.execute('SELECT sample_id, status, issues FROM sample_stats')
        
        for row in cursor.fetchall():
            sample_id = row[0]
            status = row[1] or 'ok'
            issues_str = row[2] or '[]'
            
            result['total_samples'] += 1
            
            if status == 'ok':
                result['passed_samples'] += 1
            else:
                try:
                    issues = json.loads(issues_str)
                    for issue in issues:
                        # 确定问题级别
                        level = ISSUE_LEVELS.get(issue, LEVEL_WARNING)
                        level_key = 'fatal' if level == LEVEL_FATAL else 'warning'
                        
                        # 添加到对应级别
                        if issue not in result[level_key]:
                            result[level_key][issue] = []
                        result[level_key][issue].append(sample_id)
                except:
                    pass
        
        conn.close()
        return result
    
    def get_samples_by_issue(self, issue_type):
        """
        获取指定问题类型的样本列表
        
        Args:
            issue_type: 问题类型（如 'empty_mask', 'corrupt_file' 等）
        
        Returns:
            list: 样本ID列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT sample_id, issues FROM sample_stats WHERE issues IS NOT NULL')
        
        samples = []
        for row in cursor.fetchall():
            sample_id = row[0]
            issues_str = row[1] or '[]'
            
            try:
                issues = json.loads(issues_str)
                if issue_type in issues:
                    samples.append(sample_id)
            except:
                pass
        
        conn.close()
        return samples


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
        self.images_dir = None
        self.labels_dir = None
        
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
    
    def set_directories(self, images_dir, labels_dir):
        """设置图像和标签目录"""
        self.images_dir = images_dir
        self.labels_dir = labels_dir
    
    def is_cache_valid(self, samples_info):
        """检查缓存是否有效"""
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
    
    def get_health_check_issues(self):
        """获取健康检查问题汇总"""
        if self.database is None:
            return None
        return self.database.get_health_check_issues()
    
    def start_calculation(self, samples_info, images_dir=None, labels_dir=None):
        """
        启动后台进程计算元数据（全能分析）
        
        Args:
            samples_info: [(sample_id, dataset_type), ...]
            images_dir: 图像目录（可选，使用已设置的目录）
            labels_dir: 标签目录（可选，使用已设置的目录）
        """
        # 停止之前的计算
        self.stop_calculation()
        
        if self.database is None:
            return
        
        # 使用传入的目录或已设置的目录
        images_dir = images_dir or self.images_dir
        labels_dir = labels_dir or self.labels_dir
        
        if not images_dir or not labels_dir:
            print("⚠️ 未设置图像或标签目录")
            return
        
        # 检查哪些样本需要计算
        cached_ids = self.database.get_sample_ids()
        samples_to_process = []
        
        image_exts = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp']
        label_exts = ['.png', '.tif', '.tiff', '.jpg', '.jpeg', '.bmp']
        
        for sample_id, dataset_type in samples_info:
            if sample_id in cached_ids:
                continue  # 已缓存，跳过
            
            # 查找图像文件
            image_path = None
            for ext in image_exts:
                path = os.path.join(images_dir, f"{sample_id}{ext}")
                if os.path.exists(path):
                    image_path = path
                    break
            
            # 查找标签文件
            label_path = None
            for ext in label_exts:
                path = os.path.join(labels_dir, f"{sample_id}{ext}")
                if os.path.exists(path):
                    label_path = path
                    break
            
            samples_to_process.append((sample_id, dataset_type, image_path, label_path))
        
        if not samples_to_process:
            print("✅ 所有样本已缓存，无需计算")
            self.signals.finished.emit()
            return
        
        self._total_samples = len(samples_to_process)
        print(f"🔄 启动后台进程分析 {self._total_samples} 个样本...")
        
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
                print(f"✅ 全能分析完成，共处理 {msg['processed']} 个样本")
                self.signals.finished.emit()
                break
            elif msg['type'] == 'error':
                print(f"⚠️ 分析错误: {msg['message']}")
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
