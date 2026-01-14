mmseg_params = {
    "Model": {
        "backbone": {
            "value": "ResNet50",
            "type": "select",
            "options": ["ResNet50", "Swin-T"],
            "help_text": "Backbone architecture for feature extraction.",
        },
        "decode_head": {
            "value": "ASPP",
            "type": "select",
            "options": ["ASPP", "FPN"],
            "help_text": "Segmentation head to decode feature maps.",
        },
    },
    "Remote Sensing Data": {
        "num_classes": {
            "value": 2,
            "type": "int",
            "options": [],
            "help_text": "Number of segmentation classes (including background).",
        },
        "crop_size": {
            "value": 512,
            "type": "int",
            "options": [],
            "help_text": "Patch crop size (square) for training.",
        },
        "input_channels": {
            "value": 3,
            "type": "int",
            "options": [],
            "help_text": "Number of input channels (e.g., 3 RGB or 4 RGBNIR).",
        },
        "ignore_index": {
            "value": 255,
            "type": "int",
            "options": [],
            "help_text": "Label value to ignore during loss computation.",
        },
        "data_root": {
            "value": "./data",
            "type": "lineedit",
            "options": [],
            "help_text": "Root directory of the dataset.",
        },
        "img_dir": {
            "value": "img_dir/train",
            "type": "lineedit",
            "options": [],
            "help_text": "Relative path to training images directory.",
        },
        "ann_dir": {
            "value": "ann_dir/train",
            "type": "lineedit",
            "options": [],
            "help_text": "Relative path to training annotations directory.",
        },
    },
    "Training Schedule": {
        "learning_rate": {
            "value": 0.001,
            "type": "float",
            "options": [],
            "help_text": "Base learning rate for optimizer.",
        },
        "optimizer": {
            "value": "SGD",
            "type": "select",
            "options": ["SGD", "AdamW"],
            "help_text": "Optimizer type for training.",
        },
        "max_iters": {
            "value": 80000,
            "type": "int",
            "options": [],
            "help_text": "Total training iterations.",
        },
        "batch_size": {
            "value": 8,
            "type": "int",
            "options": [],
            "help_text": "Batch size per iteration.",
        },
    },
    "Runtime": {
        "checkpoint_interval": {
            "value": 1000,
            "type": "int",
            "options": [],
            "help_text": "Save checkpoint every N iterations.",
        },
        "log_interval": {
            "value": 50,
            "type": "int",
            "options": [],
            "help_text": "Log training metrics every N iterations.",
        },
    },
}