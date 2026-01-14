# -*- coding: utf-8 -*-
"""
推理错误诊断脚本
帮助诊断推理过程中的错误
"""

import sys
import traceback
from PySide6.QtWidgets import QApplication


def diagnose_import_errors():
    """诊断导入错误"""
    print("=" * 60)
    print("1. 检查模块导入")
    print("=" * 60)
    
    modules_to_check = [
        ('PySide6.QtWidgets', 'PySide6'),
        ('PySide6.QtCore', 'PySide6'),
        ('PIL', 'Pillow'),
        ('numpy', 'numpy'),
    ]
    
    all_ok = True
    for module_name, package_name in modules_to_check:
        try:
            __import__(module_name)
            print(f"✓ {module_name:30} - OK")
        except ImportError as e:
            print(f"✗ {module_name:30} - 缺失 (需要安装 {package_name})")
            print(f"  错误: {e}")
            all_ok = False
    
    return all_ok


def diagnose_inference_panel():
    """诊断推理面板"""
    print("\n" + "=" * 60)
    print("2. 检查推理面板")
    print("=" * 60)
    
    try:
        from ui.inference_panel import InferencePanel
        print("✓ InferencePanel 导入成功")
        
        # 尝试创建实例
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        panel = InferencePanel()
        print("✓ InferencePanel 实例创建成功")
        
        # 检查关键属性
        attrs_to_check = [
            'inference_model',
            'last_inference_result',
            'pushButton_runInference',
            'lineEdit_configFile',
            'lineEdit_checkpointFile',
        ]
        
        for attr in attrs_to_check:
            if hasattr(panel, attr):
                print(f"✓ 属性 {attr:30} - 存在")
            else:
                print(f"✗ 属性 {attr:30} - 缺失")
        
        return True
        
    except Exception as e:
        print(f"✗ InferencePanel 检查失败")
        print(f"  错误: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False


def diagnose_inference_engine():
    """诊断推理引擎"""
    print("\n" + "=" * 60)
    print("3. 检查推理引擎")
    print("=" * 60)
    
    try:
        from core.inference_engine import InferenceEngine
        print("✓ InferenceEngine 导入成功")
        
        # 创建模拟模型信息
        model_info = {
            'config': 'test_config.py',
            'checkpoint': 'test_checkpoint.pth',
            'device': 'cpu',
            'classes': ['background', 'class1'],
            'palette': [[0, 0, 0], [255, 0, 0]]
        }
        
        engine = InferenceEngine(model_info)
        print("✓ InferenceEngine 实例创建成功")
        
        # 检查方法
        methods_to_check = [
            'sliding_window_inference',
            'resize_inference',
            'run_inference',
        ]
        
        for method in methods_to_check:
            if hasattr(engine, method):
                print(f"✓ 方法 {method:30} - 存在")
            else:
                print(f"✗ 方法 {method:30} - 缺失")
        
        return True
        
    except Exception as e:
        print(f"✗ InferenceEngine 检查失败")
        print(f"  错误: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False


def diagnose_pil_settings():
    """诊断PIL设置"""
    print("\n" + "=" * 60)
    print("4. 检查PIL设置")
    print("=" * 60)
    
    try:
        from PIL import Image
        print(f"✓ PIL 导入成功")
        print(f"  当前像素限制: {Image.MAX_IMAGE_PIXELS:,} 像素")
        
        if Image.MAX_IMAGE_PIXELS >= 10000000000:
            print(f"✓ 像素限制已正确设置（>= 10GB）")
        else:
            print(f"⚠️  像素限制较低，可能无法处理超大图像")
        
        return True
        
    except Exception as e:
        print(f"✗ PIL 检查失败")
        print(f"  错误: {e}")
        return False


def diagnose_config_parser():
    """诊断配置解析器"""
    print("\n" + "=" * 60)
    print("5. 检查配置解析器")
    print("=" * 60)
    
    try:
        from core.config_parser import ConfigParser
        print("✓ ConfigParser 导入成功")
        
        parser = ConfigParser()
        print("✓ ConfigParser 实例创建成功")
        
        return True
        
    except Exception as e:
        print(f"✗ ConfigParser 检查失败")
        print(f"  错误: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False


def run_simple_inference_test():
    """运行简单的推理测试"""
    print("\n" + "=" * 60)
    print("6. 运行简单推理测试")
    print("=" * 60)
    
    try:
        from core.inference_engine import InferenceEngine
        import numpy as np
        from PIL import Image
        import tempfile
        import os
        
        # 创建临时测试图像
        test_image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_path = temp_file.name
        temp_file.close()
        
        Image.fromarray(test_image).save(temp_path)
        print(f"✓ 创建测试图像: {temp_path}")
        
        # 创建推理引擎
        model_info = {
            'config': 'test_config.py',
            'checkpoint': 'test_checkpoint.pth',
            'device': 'cpu',
            'classes': ['background', 'class1'],
            'palette': [[0, 0, 0], [255, 0, 0]]
        }
        
        engine = InferenceEngine(model_info)
        print("✓ 创建推理引擎")
        
        # 测试滑窗推理
        print("\n测试滑窗推理...")
        result = engine.sliding_window_inference(
            temp_path,
            crop_size=64,
            stride=32,
            batch_size=1,
            enable_tta=False
        )
        
        if result.get('success'):
            print("✓ 滑窗推理测试成功")
            print(f"  图像尺寸: {result.get('image_shape')}")
            print(f"  策略: {result.get('strategy')}")
        else:
            print(f"✗ 滑窗推理测试失败: {result.get('error')}")
        
        # 测试全图缩放推理
        print("\n测试全图缩放推理...")
        result = engine.resize_inference(
            temp_path,
            enable_tta=False
        )
        
        if result.get('success'):
            print("✓ 全图缩放推理测试成功")
            print(f"  图像尺寸: {result.get('image_shape')}")
            print(f"  策略: {result.get('strategy')}")
        else:
            print(f"✗ 全图缩放推理测试失败: {result.get('error')}")
        
        # 清理
        os.unlink(temp_path)
        print("\n✓ 清理测试文件")
        
        return True
        
    except Exception as e:
        print(f"✗ 推理测试失败")
        print(f"  错误: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("推理错误诊断工具")
    print("=" * 60)
    print()
    
    results = []
    
    # 运行所有诊断
    results.append(("模块导入", diagnose_import_errors()))
    results.append(("推理面板", diagnose_inference_panel()))
    results.append(("推理引擎", diagnose_inference_engine()))
    results.append(("PIL设置", diagnose_pil_settings()))
    results.append(("配置解析器", diagnose_config_parser()))
    results.append(("推理测试", run_simple_inference_test()))
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name:20} - {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有检查通过！推理功能应该可以正常工作。")
        print("\n如果仍然遇到错误，请提供：")
        print("1. 完整的错误堆栈信息")
        print("2. 使用的图像信息（尺寸、格式）")
        print("3. 推理配置参数")
    else:
        print("❌ 发现问题！请根据上述错误信息进行修复。")
        print("\n常见解决方案：")
        print("1. 安装缺失的依赖: pip install pillow numpy PySide6")
        print("2. 检查文件路径是否正确")
        print("3. 确保core和ui目录存在")
    print("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n诊断已取消")
    except Exception as e:
        print(f"\n\n诊断工具本身出错: {e}")
        traceback.print_exc()
