
# 由 RS-Seg-GUI 自动生成
# Timestamp: 2025-12-19 01:06:59

# 1. 基础配置继承
_base_ = [
    '../_base_/models/swin_tiny.py',
    '../_base_/datasets/custom.py',
    '../_base_/default_runtime.py',
    '../_base_/schedules/schedule_80k.py'
]

# 2. 模型参数覆盖
model = dict(
    decode_head=dict(num_classes=2),
    auxiliary_head=dict(num_classes=2),
    # 遥感特有：如果输入不是 RGB (3通道)，需要修改 input_channels
    backbone=dict(in_channels=3) 
)

# 3. 数据管线配置
data = dict(
    samples_per_gpu=8,
    workers_per_gpu=4,
    train=dict(
        data_root='./data',
        img_dir='img_dir/train',
        ann_dir='ann_dir/train',
        pipeline=[
            dict(type='LoadImageFromFile'),
            dict(type='LoadAnnotations'),
            dict(type='Resize', img_scale=(512, 512), ratio_range=(0.5, 2.0)),
            dict(type='RandomCrop', crop_size=(512, 512), cat_max_ratio=0.75),
            dict(type='RandomFlip', prob=0.5),
            dict(type='Normalize', **{'mean': [123.675, 116.28, 103.53], 'std': [58.395, 57.12, 57.375], 'to_rgb': True}),
            dict(type='Pad', size=(512, 512), pad_val=0, seg_pad_val=255),
            dict(type='DefaultFormatBundle'),
            dict(type='Collect', keys=['img', 'gt_semantic_seg']),
        ]
    )
)

# 4. 优化器与训练策略
optimizer = dict(type='AdamW', lr=0.001, momentum=0.9, weight_decay=0.0005)
runner = dict(type='IterBasedRunner', max_iters=80000)
checkpoint_config = dict(by_epoch=False, interval=1000)
evaluation = dict(interval=50, metric='mIoU', pre_eval=True)