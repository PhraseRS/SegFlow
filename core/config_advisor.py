# -*- coding: utf-8 -*-
"""
配置顾问 (Config Advisor)

基于数据集统计信息，自动推荐 MMSegmentation 训练配置参数。
包含 DatasetInsights 数据结构和 ConfigAdvisor 推荐引擎。

Phase 3 of Roadmap: 数据分析反哺训练配置 (Data-Driven Configuration)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math


@dataclass
class DatasetInsights:
    """
    数据集洞察数据结构 (Roadmap 3.1)
    
    封装从 MetadataDatabase 提取的分析结果，
    作为 ConfigAdvisor 的输入。
    """
    # 类别信息
    class_names: List[str] = field(default_factory=list)
    
    # 类别像素分布 {class_id_str: total_pixels}
    pixel_distribution: Dict[str, int] = field(default_factory=dict)
    
    # 类别像素比例 {class_id_str: ratio}  (0.0 ~ 1.0)
    pixel_ratios: Dict[str, float] = field(default_factory=dict)
    
    # 各类别出现在多少张图像中 {class_id_str: image_count}
    image_counts: Dict[str, int] = field(default_factory=dict)
    
    # 建议类别权重 {class_id_str: weight}
    suggested_class_weights: Dict[str, float] = field(default_factory=dict)
    
    # 空标签样本占比
    empty_mask_ratio: float = 0.0
    
    # 小目标类别比例（像素占比 < 1% 的类别数 / 总类别数）
    small_object_ratio: float = 0.0
    
    # 基本统计
    total_samples: int = 0
    train_count: int = 0
    val_count: int = 0
    test_count: int = 0
    
    # 尺寸统计
    min_size: Tuple[int, int] = (0, 0)   # (width, height)
    max_size: Tuple[int, int] = (0, 0)
    avg_size: Tuple[int, int] = (0, 0)   # 平均尺寸 (width, height)
    
    # 通道数（遥感多光谱支持）
    num_channels: int = 3
    
    # 健康检查
    fatal_issues_count: int = 0
    warning_issues_count: int = 0
    
    @property
    def num_classes(self) -> int:
        """类别数量"""
        if self.class_names:
            return len(self.class_names)
        return len(self.pixel_distribution)
    
    @property
    def is_imbalanced(self) -> bool:
        """是否存在严重的类别不平衡（最大/最小像素比 > 50）"""
        if not self.pixel_ratios:
            return False
        ratios = [v for v in self.pixel_ratios.values() if v > 0]
        if len(ratios) < 2:
            return False
        return max(ratios) / min(ratios) > 50
    
    @property
    def has_small_objects(self) -> bool:
        """是否存在小目标类别"""
        return self.small_object_ratio > 0.2  # 超过 20% 的类别是小目标


class ConfigAdvisor:
    """
    配置顾问 (Roadmap 3.2)
    
    根据 DatasetInsights 自动推荐 MMSegmentation 配置参数。
    """
    
    # 类别不平衡阈值
    IMBALANCE_RATIO_THRESHOLD = 10
    
    # 小目标像素占比阈值
    SMALL_OBJECT_PIXEL_THRESHOLD = 0.01  # 1%
    
    # 空标签样本占比阈值
    EMPTY_MASK_THRESHOLD = 0.1  # 10%
    
    def __init__(self, insights: DatasetInsights):
        self.insights = insights
    
    @classmethod
    def from_database(cls, database) -> 'ConfigAdvisor':
        """
        从 MetadataDatabase 构建 ConfigAdvisor。
        
        Args:
            database: MetadataDatabase 实例
            
        Returns:
            ConfigAdvisor 实例
        """
        stats = database.get_aggregated_stats()
        health = database.get_health_check_issues()
        
        insights = DatasetInsights()
        
        # 基本统计
        insights.total_samples = stats.get('total_samples', 0)
        insights.train_count = stats.get('train_count', 0)
        insights.val_count = stats.get('val_count', 0)
        insights.test_count = stats.get('test_count', 0)
        
        # 类别分布
        insights.pixel_distribution = stats.get('class_distribution', {})
        insights.image_counts = stats.get('image_counts', {})
        
        # 计算像素比例
        total_pixels = sum(insights.pixel_distribution.values())
        if total_pixels > 0:
            insights.pixel_ratios = {
                k: v / total_pixels 
                for k, v in insights.pixel_distribution.items()
            }
        
        # 计算建议权重（中值频率平衡法）
        insights.suggested_class_weights = cls._compute_class_weights(
            insights.pixel_ratios
        )
        
        # 空标签比例
        empty_mask_count = len(health.get('warning', {}).get('empty_mask', []))
        if insights.total_samples > 0:
            insights.empty_mask_ratio = empty_mask_count / insights.total_samples
        
        # 小目标比例
        small_classes = sum(
            1 for r in insights.pixel_ratios.values()
            if 0 < r < cls.SMALL_OBJECT_PIXEL_THRESHOLD
        )
        total_fg_classes = sum(
            1 for k, r in insights.pixel_ratios.items()
            if r > 0 and k != '0'  # 排除背景类
        )
        if total_fg_classes > 0:
            insights.small_object_ratio = small_classes / total_fg_classes
        
        # 尺寸统计
        size_stats = stats.get('size_stats', {})
        insights.min_size = (
            size_stats.get('min_width', 0),
            size_stats.get('min_height', 0)
        )
        insights.max_size = (
            size_stats.get('max_width', 0),
            size_stats.get('max_height', 0)
        )
        # 计算平均尺寸
        widths = size_stats.get('widths', [])
        heights = size_stats.get('heights', [])
        if widths and heights:
            insights.avg_size = (
                int(sum(widths) / len(widths)),
                int(sum(heights) / len(heights))
            )
        
        # 通道数（从 stats 中获取，若有）
        insights.num_channels = stats.get('num_channels', 3)
        
        # 健康检查
        fatal_issues = health.get('fatal', {})
        warning_issues = health.get('warning', {})
        insights.fatal_issues_count = sum(
            len(v) for v in fatal_issues.values()
        )
        insights.warning_issues_count = sum(
            len(v) for v in warning_issues.values()
        )
        
        return cls(insights)
    
    @staticmethod
    def _compute_class_weights(pixel_ratios: Dict[str, float]) -> Dict[str, float]:
        """
        使用中值频率平衡法计算类别权重。
        
        weight_c = median(freq) / freq_c
        
        Args:
            pixel_ratios: {class_id: ratio}
            
        Returns:
            {class_id: weight}
        """
        if not pixel_ratios:
            return {}
        
        # 过滤掉零频率
        non_zero = {k: v for k, v in pixel_ratios.items() if v > 0}
        if not non_zero:
            return {k: 1.0 for k in pixel_ratios}
        
        freqs = sorted(non_zero.values())
        n = len(freqs)
        median_freq = freqs[n // 2] if n % 2 == 1 else (freqs[n//2 - 1] + freqs[n//2]) / 2
        
        weights = {}
        for class_id, ratio in pixel_ratios.items():
            if ratio > 0:
                w = median_freq / ratio
                # 限制权重范围 [0.1, 20.0]
                weights[class_id] = round(max(0.1, min(20.0, w)), 2)
            else:
                weights[class_id] = 1.0
        
        return weights
    
    def recommend_loss_config(self) -> Dict:
        """
        推荐损失函数配置 (Roadmap 3.2)
        
        决策逻辑：
        - 不平衡 → CrossEntropyLoss + class_weight
        - 极度不平衡 + 小目标 → 使用 FocalLoss
        - 否则 → 默认 CrossEntropyLoss
        
        Returns:
            dict: MMSeg 格式的 loss 配置字典
        """
        ins = self.insights
        
        if not ins.is_imbalanced:
            return {
                'type': 'CrossEntropyLoss',
                'use_sigmoid': False,
                'loss_weight': 1.0,
                '_reason': '类别分布相对均衡，使用默认交叉熵损失'
            }
        
        # 构建权重列表（按 class_id 排序）
        sorted_ids = sorted(ins.suggested_class_weights.keys(), key=lambda x: int(x))
        class_weight = [ins.suggested_class_weights.get(cid, 1.0) for cid in sorted_ids]
        
        if ins.has_small_objects:
            return {
                'type': 'FocalLoss',
                'use_sigmoid': False,
                'gamma': 2.0,
                'alpha': 0.25,
                'loss_weight': 1.0,
                'class_weight': class_weight,
                '_reason': (
                    f'检测到严重类别不平衡（{ins.small_object_ratio:.0%} 的前景类像素占比 < 1%），'
                    f'推荐使用 FocalLoss + class_weight'
                )
            }
        else:
            return {
                'type': 'CrossEntropyLoss',
                'use_sigmoid': False,
                'loss_weight': 1.0,
                'class_weight': class_weight,
                '_reason': (
                    f'检测到类别不平衡，推荐使用带 class_weight 的 CrossEntropyLoss。'
                    f'权重基于中值频率平衡法计算。'
                )
            }
    
    def recommend_augmentation(self) -> Dict:
        """
        推荐数据增强配置 (Roadmap 3.2)
        
        决策逻辑：
        - 空标签比例高 → 推荐 RandomCrop 约束
        - 小目标比例高 → 推荐 CopyPaste 增强
        - 尺寸差异大 → 推荐 Resize + RandomCrop
        
        Returns:
            dict: 推荐的数据增强配置
        """
        ins = self.insights
        recommendations = {
            'augmentations': [],
            '_reasons': []
        }
        
        # 基础增强（始终推荐）
        recommendations['augmentations'].extend([
            {'type': 'RandomFlip', 'prob': 0.5, 'direction': 'horizontal'},
            {'type': 'PhotoMetricDistortion'},
        ])
        
        # 空标签比例高 → RandomCrop 约束
        if ins.empty_mask_ratio > self.EMPTY_MASK_THRESHOLD:
            # 推荐使用 cat_max_ratio 来限制空标签样本出现频率
            crop_size = self._recommend_crop_size()
            recommendations['augmentations'].append({
                'type': 'RandomCrop',
                'crop_size': crop_size,
                'cat_max_ratio': 0.75,
            })
            recommendations['_reasons'].append(
                f'空标签样本占比 {ins.empty_mask_ratio:.1%}，'
                f'推荐 RandomCrop(cat_max_ratio=0.75) 减少空 patch 出现概率'
            )
        else:
            crop_size = self._recommend_crop_size()
            recommendations['augmentations'].append({
                'type': 'RandomCrop',
                'crop_size': crop_size,
            })
        
        # 小目标多 → CopyPaste 增强
        if ins.has_small_objects:
            recommendations['augmentations'].append({
                'type': 'CopyPaste',
                'max_num_pasted': 10,
                'paste_by_box': False,
            })
            recommendations['_reasons'].append(
                f'小目标类别占前景类 {ins.small_object_ratio:.0%}，'
                f'推荐 CopyPaste 增强小目标出现频率'
            )
        
        # 尺寸差异大 → 多尺度训练
        w_range = ins.max_size[0] - ins.min_size[0]
        h_range = ins.max_size[1] - ins.min_size[1]
        if w_range > 500 or h_range > 500:
            recommendations['augmentations'].append({
                'type': 'Resize',
                'scale': (2048, 512),
                'keep_ratio': True,
            })
            recommendations['_reasons'].append(
                f'图像尺寸跨度大 (W: {ins.min_size[0]}-{ins.max_size[0]}, '
                f'H: {ins.min_size[1]}-{ins.max_size[1]})，推荐多尺度训练'
            )
        
        if not recommendations['_reasons']:
            recommendations['_reasons'].append('数据集分布较均衡，使用标准数据增强配置')
        
        return recommendations
    
    def _recommend_crop_size(self) -> Tuple[int, int]:
        """根据图像尺寸推荐裁剪大小"""
        ins = self.insights
        min_dim = min(ins.min_size[0], ins.min_size[1]) if min(ins.min_size) > 0 else 512
        
        # 裁剪大小为最小维度的 80%，对齐到 32 的倍数
        crop_dim = int(min_dim * 0.8)
        crop_dim = max(256, (crop_dim // 32) * 32)
        crop_dim = min(crop_dim, 1024)
        
        return (crop_dim, crop_dim)
    
    def recommend_rs_params(self) -> Dict:
        """
        遥感专用推荐参数（Training Roadmap Task 2.1）
        
        聚合所有推荐结果为单一字典，供 UI 层和 MMSegTrainer.generate_config() 消费。
        
        Returns:
            dict: {
                'in_channels': int,
                'crop_size': (int, int),
                'class_weight': list,
                'loss_config': dict,
                'augmentation': dict,
            }
        """
        ins = self.insights
        
        # 类别权重列表（按 class_id 排序）
        sorted_ids = sorted(
            ins.suggested_class_weights.keys(),
            key=lambda x: int(x)
        )
        class_weight = [
            ins.suggested_class_weights.get(cid, 1.0)
            for cid in sorted_ids
        ]
        
        return {
            'in_channels': ins.num_channels,
            'crop_size': self._recommend_crop_size(),
            'class_weight': class_weight,
            'loss_config': self.recommend_loss_config(),
            'augmentation': self.recommend_augmentation(),
        }
    
    def get_summary(self) -> str:
        """
        生成人类可读的推荐摘要。
        
        Returns:
            str: 推荐配置摘要文本
        """
        ins = self.insights
        lines = [
            '📊 数据集洞察摘要',
            '='*40,
            f'总样本数: {ins.total_samples} '
            f'(训练={ins.train_count}, 验证={ins.val_count}, 测试={ins.test_count})',
            f'类别数: {ins.num_classes}',
            f'类别不平衡: {"⚠️ 是" if ins.is_imbalanced else "✅ 否"}',
            f'小目标类别占比: {ins.small_object_ratio:.0%}',
            f'空标签样本占比: {ins.empty_mask_ratio:.1%}',
            f'健康问题: 🔴 {ins.fatal_issues_count} | 🟠 {ins.warning_issues_count}',
            '',
            '💡 推荐配置',
            '-'*40,
        ]
        
        loss_config = self.recommend_loss_config()
        lines.append(f'损失函数: {loss_config["type"]}')
        lines.append(f'  原因: {loss_config["_reason"]}')
        
        aug_config = self.recommend_augmentation()
        lines.append(f'数据增强: {len(aug_config["augmentations"])} 个操作')
        for reason in aug_config['_reasons']:
            lines.append(f'  • {reason}')
        
        return '\n'.join(lines)
