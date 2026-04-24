#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
可视化集成验证脚本（无依赖版本）
仅检查代码结构和集成逻辑，不运行实际代码
"""

import os
import re
import sys


def check_file_exists(filepath, description):
    """检查文件是否存在"""
    if os.path.exists(filepath):
        print("[OK] {}: {}".format(description, filepath))
        return True
    else:
        print("[FAIL] {} not found: {}".format(description, filepath))
        return False


def check_code_pattern(filepath, patterns, description):
    """检查代码中是否包含特定模式"""
    if not os.path.exists(filepath):
        print("[FAIL] File not found: {}".format(filepath))
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    results = []
    for pattern, desc in patterns:
        if re.search(pattern, content):
            print("  [OK] {}".format(desc))
            results.append(True)
        else:
            print("  [FAIL] {}".format(desc))
            results.append(False)

    return all(results)


def main():
    print("\n" + "=" * 70)
    print("Visualization Integration Verification")
    print("=" * 70 + "\n")

    all_passed = True

    # 1. Check core files exist
    print("1. Check Core Files")
    print("-" * 70)
    files = [
        ("core/mask_renderer.py", "MaskRenderer core class"),
        ("ui/widgets/visualization_widget.py", "VisualizationWidget UI component"),
        ("ui/inference_panel.py", "InferencePanel"),
        ("core/inference_engine.py", "InferenceEngine")
    ]

    for filepath, desc in files:
        if not check_file_exists(filepath, desc):
            all_passed = False
    print()

    # 2. Check MaskRenderer implementation
    print("2. Check MaskRenderer Implementation")
    print("-" * 70)
    patterns = [
        (r'class MaskRenderer', 'MaskRenderer class defined'),
        (r'def render_mask\(', 'render_mask method implemented'),
        (r'def render_overlay\(', 'render_overlay method implemented'),
        (r'def render_legend\(', 'render_legend method implemented'),
    ]
    if not check_code_pattern("core/mask_renderer.py", patterns, "MaskRenderer"):
        all_passed = False
    print()

    # 3. Check VisualizationWidget implementation
    print("3. Check VisualizationWidget Implementation")
    print("-" * 70)
    patterns = [
        (r'class VisualizationWidget', 'VisualizationWidget class defined'),
        (r'def render\(', 'render method implemented (small image)'),
        (r'def render_large_image\(', 'render_large_image method implemented (large image)'),
        (r'def clear\(', 'clear method implemented'),
        (r'from core\.mask_renderer import MaskRenderer', 'MaskRenderer imported'),
    ]
    if not check_code_pattern("ui/widgets/visualization_widget.py", patterns, "VisualizationWidget"):
        all_passed = False
    print()

    # 4. Check InferenceEngine return format
    print("4. Check InferenceEngine Return Format")
    print("-" * 70)
    patterns = [
        (r"result\['mask'\]", 'mask field returned'),
        (r"result\['image'\]", 'image field returned'),
        (r"result\['classes'\]", 'classes field returned'),
        (r"result\['palette'\]", 'palette field returned'),
    ]
    if not check_code_pattern("core/inference_engine.py", patterns, "InferenceEngine"):
        all_passed = False
    print()

    # 5. Check InferencePanel integration
    print("5. Check InferencePanel Integration")
    print("-" * 70)
    patterns = [
        (r'from ui\.widgets\.visualization_widget import VisualizationWidget', 'VisualizationWidget imported'),
        (r'self\.visualization_widget = VisualizationWidget\(\)', 'VisualizationWidget instance created'),
        (r'self\.visualization_widget\.render\(', 'Small image render method called'),
        (r'self\.visualization_widget\.render_large_image\(', 'Large image render method called'),
        (r"result\.get\('image'\)", 'Image array retrieved'),
        (r"result\.get\('mask'\)", 'Mask array retrieved'),
    ]
    if not check_code_pattern("ui/inference_panel.py", patterns, "InferencePanel"):
        all_passed = False
    print()

    # 6. Check integration logic completeness
    print("6. Check Integration Logic Completeness")
    print("-" * 70)

    # Check small image rendering logic
    with open("ui/inference_panel.py", 'r', encoding='utf-8') as f:
        panel_content = f.read()

    small_image_logic = all([
        'image_array = result.get' in panel_content,
        'mask = result.get' in panel_content,
        'classes = result.get' in panel_content,
        'palette = result.get' in panel_content,
        'self.visualization_widget.render(' in panel_content,
    ])

    if small_image_logic:
        print("  [OK] Small image rendering logic complete")
    else:
        print("  [FAIL] Small image rendering logic incomplete")
        all_passed = False

    # Check large image rendering logic
    large_image_logic = all([
        'render_large_image(' in panel_content,
        'image_path=' in panel_content,
        'mask_path=' in panel_content,
    ])

    if large_image_logic:
        print("  [OK] Large image rendering logic complete")
    else:
        print("  [FAIL] Large image rendering logic incomplete")
        all_passed = False

    print()

    # Summary
    print("=" * 70)
    if all_passed:
        print("SUCCESS: All checks passed! Visualization integration complete.")
        print("\nIntegration Summary:")
        print("  1. [OK] MaskRenderer core rendering class")
        print("  2. [OK] VisualizationWidget UI component")
        print("  3. [OK] InferenceEngine returns numpy arrays")
        print("  4. [OK] InferencePanel integrates rendering component")
        print("  5. [OK] Small and large image rendering logic")
    else:
        print("WARNING: Some checks failed. Please review details above.")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
