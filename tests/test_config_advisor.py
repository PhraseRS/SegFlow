# -*- coding: utf-8 -*-
"""
测试 ConfigAdvisor 和 DatasetInsights
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_advisor import DatasetInsights, ConfigAdvisor


def test_dataset_insights_defaults():
    """测试 DatasetInsights 默认值"""
    ins = DatasetInsights()
    assert ins.num_classes == 0
    assert ins.is_imbalanced is False
    assert ins.has_small_objects is False
    assert ins.empty_mask_ratio == 0.0
    print("✅ DatasetInsights 默认值测试通过")


def test_class_weight_computation():
    """测试中值频率平衡法权重计算"""
    pixel_ratios = {
        '0': 0.80,   # 背景类，占 80%
        '1': 0.15,   # 类别1，占 15%
        '2': 0.04,   # 类别2，占 4%
        '3': 0.01,   # 类别3，占 1%
    }
    
    weights = ConfigAdvisor._compute_class_weights(pixel_ratios)
    
    assert '0' in weights
    assert '1' in weights
    assert '2' in weights
    assert '3' in weights
    
    # 背景类权重应最低，小目标类权重应最高
    assert weights['0'] < weights['3'], f"背景类权重 {weights['0']} 不应大于小目标类 {weights['3']}"
    
    # 所有权重应在 [0.1, 20.0] 范围内
    for w in weights.values():
        assert 0.1 <= w <= 20.0, f"权重 {w} 超出 [0.1, 20.0] 范围"
    
    print(f"✅ 类别权重计算测试通过: {weights}")


def test_balanced_dataset_recommendation():
    """测试均衡数据集的推荐配置"""
    ins = DatasetInsights(
        pixel_distribution={'0': 500, '1': 400, '2': 300},
        pixel_ratios={'0': 0.42, '1': 0.33, '2': 0.25},
        total_samples=100,
        train_count=80,
        val_count=20,
    )
    
    advisor = ConfigAdvisor(ins)
    loss = advisor.recommend_loss_config()
    
    assert loss['type'] == 'CrossEntropyLoss'
    assert 'class_weight' not in loss, "均衡数据集不应推荐 class_weight"
    
    print(f"✅ 均衡数据集推荐测试通过: {loss['type']}")


def test_imbalanced_dataset_recommendation():
    """测试极度不平衡数据集的推荐配置"""
    ins = DatasetInsights(
        pixel_distribution={'0': 8000, '1': 1500, '2': 400, '3': 50, '4': 10},
        pixel_ratios={'0': 0.80, '1': 0.15, '2': 0.04, '3': 0.005, '4': 0.001},
        suggested_class_weights={'0': 0.1, '1': 0.5, '2': 1.9, '3': 15.0, '4': 20.0},
        small_object_ratio=0.5,  # 50% 的前景类是小目标
        total_samples=100,
        train_count=80,
        val_count=20,
    )
    
    advisor = ConfigAdvisor(ins)
    loss = advisor.recommend_loss_config()
    
    # 极度不平衡 + 小目标 → FocalLoss
    assert loss['type'] == 'FocalLoss', f"期望 FocalLoss, 得到 {loss['type']}"
    assert 'class_weight' in loss
    assert loss['gamma'] == 2.0
    
    print(f"✅ 不平衡数据集推荐测试通过: {loss['type']}, gamma={loss['gamma']}")


def test_augmentation_with_empty_masks():
    """测试空标签多时的增强推荐"""
    ins = DatasetInsights(
        empty_mask_ratio=0.25,  # 25% 空标签
        min_size=(512, 512),
        max_size=(1024, 1024),
        pixel_ratios={'0': 0.65, '1': 0.20, '2': 0.15},
        total_samples=100,
    )
    
    advisor = ConfigAdvisor(ins)
    aug = advisor.recommend_augmentation()
    
    # 应该包含带 cat_max_ratio 的 RandomCrop
    crop_augs = [a for a in aug['augmentations'] if a.get('type') == 'RandomCrop']
    assert len(crop_augs) == 1
    assert crop_augs[0].get('cat_max_ratio') == 0.75
    
    print(f"✅ 空标签增强推荐测试通过: cat_max_ratio={crop_augs[0].get('cat_max_ratio')}")


def test_augmentation_with_small_objects():
    """测试小目标多时的增强推荐"""
    ins = DatasetInsights(
        small_object_ratio=0.4,  # 40% 小目标
        min_size=(512, 512),
        max_size=(512, 512),
        pixel_ratios={'0': 0.90, '1': 0.005, '2': 0.005, '3': 0.09},
        total_samples=100,
    )
    
    advisor = ConfigAdvisor(ins)
    aug = advisor.recommend_augmentation()
    
    # 应该包含 CopyPaste
    copy_paste = [a for a in aug['augmentations'] if a.get('type') == 'CopyPaste']
    assert len(copy_paste) == 1
    
    print(f"✅ 小目标增强推荐测试通过: CopyPaste 已推荐")


def test_summary_generation():
    """测试摘要生成"""
    ins = DatasetInsights(
        pixel_distribution={'0': 8000, '1': 1500, '2': 400},
        pixel_ratios={'0': 0.80, '1': 0.15, '2': 0.04},
        suggested_class_weights={'0': 0.1, '1': 0.5, '2': 1.9},
        total_samples=100,
        train_count=80,
        val_count=20,
        fatal_issues_count=2,
        warning_issues_count=5,
        min_size=(256, 256),
        max_size=(512, 512),
    )
    
    advisor = ConfigAdvisor(ins)
    summary = advisor.get_summary()
    
    assert '📊' in summary
    assert 'Total Samples: 100' in summary
    assert 'Classes: 3' in summary
    
    print(f"✅ 摘要生成测试通过\n{summary}")
