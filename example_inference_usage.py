# -*- coding: utf-8 -*-
"""
推理功能使用示例
演示如何使用推理面板和推理引擎
"""

import sys
from PySide6.QtWidgets import QApplication
from ui.inference_panel import InferencePanel


def example_1_basic_usage():
    """示例1：基本使用"""
    print("=" * 60)
    print("示例1：推理面板基本使用")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    # 创建推理面板
    panel = InferencePanel()
    
    # 连接信号
    panel.log_message.connect(lambda msg: print(f"[LOG] {msg}"))
    panel.model_loaded.connect(lambda info: print(f"[EVENT] 模型已加载"))
    panel.inference_finished.connect(lambda result: print(f"[EVENT] 推理完成"))
    
    # 显示面板
    panel.show()
    
    print("\n使用步骤：")
    print("1. 点击'浏览...'选择配置文件")
    print("2. 点击'浏览...'选择权重文件")
    print("3. 点击'加载模型'")
    print("4. 选择推理策略（滑窗/全图缩放）")
    print("5. 调整推理参数")
    print("6. 点击'运行推理'并选择图像")
    
    sys.exit(app.exec())


def example_2_inference_engine():
    """示例2：直接使用推理引擎"""
    print("=" * 60)
    print("示例2：直接使用推理引擎")
    print("=" * 60)
    
    from core.inference_engine import InferenceEngine
    
    # 模拟模型信息
    model_info = {
        'config': 'path/to/config.py',
        'checkpoint': 'path/to/checkpoint.pth',
        'device': 'cuda:0',
        'classes': ['background', 'building', 'road', 'vegetation'],
        'palette': [[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255]]
    }
    
    # 创建推理引擎
    engine = InferenceEngine(model_info)
    
    # 滑窗推理
    print("\n执行滑窗推理...")
    result = engine.sliding_window_inference(
        image_path='path/to/image.png',
        crop_size=1024,
        stride=512,
        batch_size=1,
        enable_tta=False
    )
    
    if result['success']:
        print(f"✅ 推理成功")
        print(f"   图像尺寸: {result['image_shape']}")
        print(f"   策略: {result['strategy']}")
        print(f"   窗口总数: {result['params']['total_windows']}")
    else:
        print(f"❌ 推理失败: {result.get('error')}")
    
    # 全图缩放推理
    print("\n执行全图缩放推理...")
    result = engine.resize_inference(
        image_path='path/to/image.png',
        enable_tta=False
    )
    
    if result['success']:
        print(f"✅ 推理成功")
        print(f"   图像尺寸: {result['image_shape']}")
        print(f"   策略: {result['strategy']}")


def example_3_get_config():
    """示例3：获取推理配置"""
    print("=" * 60)
    print("示例3：获取推理配置")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    # 创建推理面板
    panel = InferencePanel()
    
    # 获取当前配置
    config = panel.get_inference_config()
    
    print("\n当前推理配置：")
    print(f"  配置文件: {config['config_file']}")
    print(f"  权重文件: {config['checkpoint_file']}")
    print(f"  计算设备: {config['device']}")
    print(f"  推理模式: {config['inference_mode']}")
    print(f"  策略模式: {config['strategy_mode']}")
    print(f"  窗口大小: {config['crop_size']}")
    print(f"  步长: {config['stride']}")
    print(f"  批大小: {config['batch_size']}")
    print(f"  TTA增强: {config['enable_tta']}")
    print(f"  置信度阈值: {config['conf_threshold']}")
    print(f"  导出格式: {config['export_formats']}")
    print(f"  导出目录: {config['export_dir']}")
    
    # 检查模型是否已加载
    if panel.is_model_loaded():
        print("\n✅ 模型已加载")
    else:
        print("\n⚠️  模型未加载")


def example_4_signals():
    """示例4：信号连接"""
    print("=" * 60)
    print("示例4：信号连接示例")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    # 创建推理面板
    panel = InferencePanel()
    
    # 连接所有信号
    panel.log_message.connect(
        lambda msg: print(f"📝 日志: {msg}")
    )
    
    panel.model_loaded.connect(
        lambda info: print(f"🎯 模型已加载: {info.get('model_name', 'Unknown')}")
    )
    
    panel.inference_started.connect(
        lambda: print("🚀 推理已开始")
    )
    
    panel.inference_finished.connect(
        lambda result: print(f"✅ 推理已完成: {result.get('strategy', 'unknown')}")
    )
    
    panel.inference_error.connect(
        lambda error: print(f"❌ 推理错误: {error}")
    )
    
    panel.show()
    
    print("\n信号已连接，执行推理操作时会触发相应的回调函数")
    
    sys.exit(app.exec())


def main():
    """主函数"""
    print("\n推理功能使用示例")
    print("=" * 60)
    print("请选择要运行的示例：")
    print("1. 基本使用（推荐）")
    print("2. 直接使用推理引擎")
    print("3. 获取推理配置")
    print("4. 信号连接示例")
    print("=" * 60)
    
    choice = input("\n请输入选项 (1-4): ").strip()
    
    if choice == '1':
        example_1_basic_usage()
    elif choice == '2':
        example_2_inference_engine()
    elif choice == '3':
        example_3_get_config()
    elif choice == '4':
        example_4_signals()
    else:
        print("无效的选项")


if __name__ == '__main__':
    main()
