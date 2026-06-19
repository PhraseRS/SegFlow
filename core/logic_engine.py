import os
from jinja2 import Template

# --- 1. 定义 MMSegmentation 的配置模板 ---
# 这是一个 Jinja2 模板字符串。注意 {{ }} 是变量占位符。
MMSEG_TEMPLATE_STR = """
# 由 RS-Seg-GUI 自动生成
# Timestamp: {{ timestamp }}

# 1. 基础配置继承
_base_ = [
    '../_base_/models/{{ model_backbone }}.py',
    '../_base_/datasets/{{ dataset_type }}.py',
    '../_base_/default_runtime.py',
    '../_base_/schedules/schedule_{{ max_iters // 1000 }}k.py'
]

# 2. 模型参数覆盖
model = dict(
    decode_head=dict(num_classes={{ num_classes }}),
    auxiliary_head=dict(num_classes={{ num_classes }}),
    # 遥感特有：如果输入不是 RGB (3通道)，需要修改 input_channels
    backbone=dict(in_channels={{ input_channels }}) 
)

# 3. 数据管线配置
data = dict(
    samples_per_gpu={{ batch_size }},
    workers_per_gpu=4,
    train=dict(
        data_root='{{ data_root }}',
        img_dir='{{ img_dir }}',
        ann_dir='{{ ann_dir }}',
        pipeline=[
            dict(type='LoadImageFromFile'),
            dict(type='LoadAnnotations'),
            dict(type='Resize', img_scale=({{ crop_size }}, {{ crop_size }}), ratio_range=(0.5, 2.0)),
            dict(type='RandomCrop', crop_size=({{ crop_size }}, {{ crop_size }}), cat_max_ratio=0.75),
            dict(type='RandomFlip', prob=0.5),
            dict(type='Normalize', **{{ normalize_cfg }}),
            dict(type='Pad', size=({{ crop_size }}, {{ crop_size }}), pad_val=0, seg_pad_val=255),
            dict(type='DefaultFormatBundle'),
            dict(type='Collect', keys=['img', 'gt_semantic_seg']),
        ]
    )
)

# 4. 优化器与训练策略
optimizer = dict(type='{{ optimizer }}', lr={{ learning_rate }}, momentum=0.9, weight_decay=0.0005)
runner = dict(type='IterBasedRunner', max_iters={{ max_iters }})
checkpoint_config = dict(by_epoch=False, interval={{ checkpoint_interval }})
evaluation = dict(interval={{ eval_interval }}, metric='mIoU', pre_eval=True)
"""

class ConfigGenerator:
    def __init__(self):
        self.errors = [] # 收集错误信息

    def _flatten_config(self, nested_data):
        """
        将嵌套的配置字典展平为简单的 key-value 对
        输入格式: {section: {key: {value: ..., type: ..., ...}}}
        输出格式: {key: value}
        """
        flat = {}
        for section, params in nested_data.items():
            for key, info in params.items():
                if isinstance(info, dict) and 'value' in info:
                    flat[key] = info['value']
                else:
                    flat[key] = info
        return flat

    def validate(self, ui_data):
        """
        业务逻辑校验层
        返回: (bool, error_msg_list)
        """
        self.errors = []
        
        # 如果是嵌套结构，先展平
        if any(isinstance(v, dict) and 'value' in v for section in ui_data.values() if isinstance(section, dict) for v in section.values()):
            flat_data = self._flatten_config(ui_data)
        else:
            flat_data = ui_data
        
        # Rule 1: 遥感切片大小必须是 32 的倍数 (Backbone 下采样限制)
        crop = int(flat_data.get('crop_size', 512))
        if crop % 32 != 0:
            self.errors.append(f"Crop Size ({crop}) must be a multiple of 32 (e.g. 256, 512, 1024), otherwise inference will fail.")
            
        # Rule 2: 学习率检查
        lr = float(flat_data.get('learning_rate', 0.01))
        if lr <= 0:
            self.errors.append("Learning Rate must be greater than 0.")

        return len(self.errors) == 0, self.errors

    def generate(self, ui_data, output_path="work_dirs/gen_config.py"):
        """
        渲染模板并保存文件
        """
        # 1. 准备渲染上下文 (Context Preparation)
        # 如果是嵌套结构，先展平
        if any(isinstance(v, dict) and 'value' in v for section in ui_data.values() if isinstance(section, dict) for v in section.values()):
            flat_data = self._flatten_config(ui_data)
        else:
            flat_data = ui_data
        
        # 映射 UI 变量名到模板变量名
        # backbone 映射: ResNet50 -> fcn_r50-d8, Swin-T -> swin_tiny
        backbone_map = {
            'ResNet50': 'fcn_r50-d8',
            'Swin-T': 'swin_tiny',
        }
        backbone_value = flat_data.get('backbone', 'ResNet50')
        model_backbone = backbone_map.get(backbone_value, 'fcn_r50-d8')
        
        # 添加时间戳
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        context = {
            'timestamp': timestamp,
            'model_backbone': model_backbone,
            'dataset_type': 'custom', # 遥感通常用 CustomDataset
            'max_iters': int(flat_data.get('max_iters', 80000)),
            'num_classes': int(flat_data.get('num_classes', 2)),
            'input_channels': int(flat_data.get('input_channels', 3)),
            'batch_size': int(flat_data.get('batch_size', 8)),
            'data_root': flat_data.get('data_root', './data'),
            'img_dir': flat_data.get('img_dir', 'img_dir/train'),
            'ann_dir': flat_data.get('ann_dir', 'ann_dir/train'),
            'crop_size': int(flat_data.get('crop_size', 512)),
            'optimizer': flat_data.get('optimizer', 'SGD'),
            'learning_rate': float(flat_data.get('learning_rate', 0.001)),
            'checkpoint_interval': int(flat_data.get('checkpoint_interval', 1000)),
            'eval_interval': int(flat_data.get('log_interval', 50)),  # 使用 log_interval 作为 eval_interval
            # 复杂对象可以直接传递 dict
            'normalize_cfg': dict(mean=[123.675, 116.28, 103.53], std=[58.395, 57.12, 57.375], to_rgb=True)
        }

        # 2. 渲染
        template = Template(MMSEG_TEMPLATE_STR)
        rendered_content = template.render(**context)

        # 3. 写入文件
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rendered_content)
        
        return output_path

# --- 测试代码 ---
if __name__ == "__main__":
    # 测试 1: 模拟从 config_editor.export_to_dict() 获取的嵌套数据结构
    mock_nested_data = {
        "Model": {
            "backbone": {"value": "ResNet50", "type": "select"},
            "decode_head": {"value": "ASPP", "type": "select"}
        },
        "Remote Sensing Data": {
            "crop_size": {"value": 512, "type": "int"},
            "input_channels": {"value": 3, "type": "int"},
            "ignore_index": {"value": 255, "type": "int"}
        },
        "Training Schedule": {
            "learning_rate": {"value": 0.001, "type": "float"},
            "optimizer": {"value": "SGD", "type": "select"},
            "max_iters": {"value": 80000, "type": "int"},
            "batch_size": {"value": 8, "type": "int"}
        },
        "Runtime": {
            "checkpoint_interval": {"value": 1000, "type": "int"},
            "log_interval": {"value": 50, "type": "int"}
        }
    }

    generator = ConfigGenerator()
    
    print("=== Test Nested Data Structure ===")
    # 1. 校验
    is_valid, errs = generator.validate(mock_nested_data)
    if not is_valid:
        print("❌ Config validation failed:")
        for e in errs: print(f" - {e}")
    else:
        print("✅ Config validation passed")
        # 2. 生成
        path = generator.generate(mock_nested_data)
        print(f"✅ Config file generated: {path}")
        print("-" * 40)
        # 打印生成的配置文件
        with open(path, 'r', encoding='utf-8') as f:
            print(f.read())
    
    print("\n" + "=" * 40)
    print("=== Test Flat Data Structure ===")
    # 测试 2: 扁平数据结构（向后兼容）
    mock_flat_data = {
        'backbone': 'Swin-T',
        'crop_size': 512,
        'learning_rate': 0.001,
        'batch_size': 8,
        'max_iters': 80000,
        'input_channels': 3,
        'optimizer': 'AdamW',
        'checkpoint_interval': 1000,
        'log_interval': 50
    }
    
    is_valid2, errs2 = generator.validate(mock_flat_data)
    if not is_valid2:
        print("❌ Config validation failed:")
        for e in errs2: print(f" - {e}")
    else:
        print("✅ Config validation passed")
        path2 = generator.generate(mock_flat_data, "work_dirs/gen_config_flat.py")
        print(f"✅ Config file generated: {path2}")