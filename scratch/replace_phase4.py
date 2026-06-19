import os

directories = ['d:/WorkSpace/RSegGUI/core', 'd:/WorkSpace/RSegGUI/utils']

replacements = {
    # config_advisor.py
    "类别数: ": "Classes: ",
    "是否存在小目标类别": "Contains Small Object Classes",
    "检测到严重类别不平衡（": "Severe class imbalance detected (",
    "是否存在严重的类别不平衡（最大/最小像素比 > 50）": "Contains severe class imbalance (max/min pixel ratio > 50)",
    "空标签样本占比: ": "Empty Mask Ratio: ",
    "损失函数: ": "Loss Function: ",
    "✅ 否": "✅ No",
    " 个操作": " operations",
    "小目标类别占比: ": "Small Object Ratio: ",
    "空标签样本占比 ": "Empty mask ratio ",
    " 的前景类像素占比 < 1%），推荐使用 FocalLoss + class_weight": "'s foreground pixel ratio < 1%), Recommend FocalLoss + class_weight",
    "💡 推荐配置": "💡 Recommended Config",
    "检测到类别不平衡，推荐使用带 class_weight 的 CrossEntropyLoss。权重基于中值频率平衡法计算。": "Class imbalance detected, recommend CrossEntropyLoss with class_weight based on median frequency balancing.",
    "小目标类别占前景类 ": "Small object classes take up ",
    "数据集分布较均衡，使用标准数据增强配置": "Balanced dataset, standard augmentation",
    "📊 数据集洞察摘要": "📊 Dataset Insights Summary",
    "类别分布相对均衡，使用默认交叉熵损失": "Class distribution relatively balanced, use default CrossEntropyLoss",
    "⚠️ 是": "⚠️ Yes",
    "数据增强: ": "Augmentation: ",
    "  原因: ": "  Reason: ",
    "健康问题: 🔴 ": "Health Issues: 🔴 ",
    "，推荐 RandomCrop(cat_max_ratio=0.75) 减少空 patch 出现概率": ", recommend RandomCrop(cat_max_ratio=0.75) to reduce empty patches",
    "图像尺寸跨度大 (W: ": "Large variance in image size (W: ",
    "类别数量": "Class Count",
    "，推荐 CopyPaste 增强小目标出现频率": ", recommend CopyPaste to enhance small object frequency",
    "根据图像尺寸推荐裁剪大小": "Recommend crop size based on image sizes",
    ")，推荐多尺度训练": "), recommend multi-scale training",
    "类别不平衡: ": "Class Imbalance: ",
    "总样本数: ": "Total Samples: ",

    # dataset_metadata.py
    "⚠️ 未设置图像或标签目录": "⚠️ Image or label directory not set",
    "⚠️ 分析错误: ": "⚠️ Analysis error: ",
    "🔄 启动后台进程分析 ": "🔄 Starting background process to analyze ",
    " 个样本...": " samples...",
    "✅ 所有样本已缓存，无需计算": "✅ All samples cached, no computation needed",
    " 个样本": " samples",
    "✅ 全能分析完成，共处理 ": "✅ Analysis complete, processed ",

    # inference_engine.py
    "[推理引擎] 🚀 使用真实模型进行推理...": "[InferenceEngine] 🚀 Inference with real model...",
    "[推理引擎] 建议：使用专业的遥感影像处理工具进行推理": "[InferenceEngine] Suggestion: Use professional RS tools for inference",
    "GDAL未安装，无法进行大图像分块推理。请安装GDAL: pip install gdal": "GDAL not installed, cannot run Tile inference. Please install GDAL: pip install gdal",
    "[推理引擎] 为避免内存溢出，将使用轻量级模式": "[InferenceEngine] To avoid OOM, using lightweight mode",
    "[推理引擎] ✅ 真实推理完成": "[InferenceEngine] ✅ Real inference complete",
    "未知的推理策略: ": "Unknown inference strategy: ",
    "[推理引擎] ⚠️  超大图像 (": "[InferenceEngine] ⚠️  Large image (",
    "[推理引擎] 设备: ": "[InferenceEngine] Device: ",
    "全图缩放推理失败: ": "Full image scale inference failed: ",
    "[推理引擎] 分块数量: ": "[InferenceEngine] Tile count: ",
    "[推理引擎] 检测到超大图像，使用轻量级模式": "[InferenceEngine] Large image detected, using lightweight mode",
    "[推理引擎] 🎯 推理模式: 真实神经网络推理": "[InferenceEngine] 🎯 Inference mode: Real neural network inference",
    "M像素)": "M pixels)",
    "[推理引擎] ⚠️  图像过大，无法生成完整掩码": "[InferenceEngine] ⚠️  Image too large, cannot generate full mask",
    "[推理引擎] ⚠️  读取原始图像失败: ": "[InferenceEngine] ⚠️  Read original image failed: ",
    "[推理引擎] 图像尺寸: ": "[InferenceEngine] Image size: ",
    "[推理引擎] ✅ 模型加载成功（真实模型）": "[InferenceEngine] ✅ Model loaded successfully (Real Model)",
    "[推理引擎] 详细错误:\\n": "[InferenceEngine] Detailed error:\\n",
    "[推理引擎] ✅ 金字塔构建成功": "[InferenceEngine] ✅ Pyramid building successful",
    "[推理引擎] 开始滑窗推理: ": "[InferenceEngine] Start sliding window inference: ",
    "\\n[推理排查] 🚨 当前正在使用此目录下的 MMSeg 代码: ": "\\n[InferenceDebug] 🚨 Currently using MMSeg code from: ",
    "大图像分块推理需要真实模型，请确保MMSegmentation已正确安装并加载模型": "Tile inference requires real model, please ensure MMSegmentation is installed and model is loaded",
    "[推理引擎] ✅ 滑窗推理完成": "[InferenceEngine] ✅ Sliding window inference complete",
    "[推理引擎] ⚠️ 金字塔构建失败，但不影响结果": "[InferenceEngine] ⚠️ Pyramid building failed, but results not affected",
    "[推理引擎] 窗口大小: ": "[InferenceEngine] Window size: ",
    "[推理引擎] 正在加载模型...": "[InferenceEngine] Loading model...",
    "[推理引擎] 总耗时: ": "[InferenceEngine] Total time: ",
    "[推理引擎] 全图缩放推理失败: ": "[InferenceEngine] Full image scale inference failed: ",
    "滑窗推理失败: ": "Sliding window inference failed: ",
    "[推理引擎] 📊 推理参数: crop=": "[InferenceEngine] 📊 Inference params: crop=",
    "[推理引擎] 权重文件: ": "[InferenceEngine] Weight file: ",
    ", 步长: ": ", stride: ",
    " 分钟": " mins",
    "[推理引擎] ⚠️  使用模拟推理（MMSegmentation未安装或模型加载失败）": "[InferenceEngine] ⚠️  Using mock inference (MMSegmentation not installed or model load failed)",
    "[推理引擎] 输入图像: ": "[InferenceEngine] Input image: ",
    ", 重叠率: ": ", overlap rate: ",
    "[推理引擎] 分块大小: ": "[InferenceEngine] Tile size: ",
    "大图像分块推理失败: ": "Large image tile inference failed: ",
    "用户取消": "User cancelled",
    "[推理引擎] 🛑 推理已取消": "[InferenceEngine] 🛑 Inference cancelled",
    "[推理引擎] ⚠️  窗口 (": "[InferenceEngine] ⚠️  Window (",
    "[推理引擎] 错误: ": "[InferenceEngine] Error: ",
    "[推理引擎] ⚠️  这不是真正的神经网络推理！": "[InferenceEngine] ⚠️  This is not real neural network inference!",
    "[推理引擎] ⚠️  MMSegmentation 未安装，使用模拟模式": "[InferenceEngine] ⚠️  MMSegmentation not installed, using mock mode",
    "[推理引擎] 配置文件: ": "[InferenceEngine] Config file: ",
    "[推理引擎] 窗口数量: ": "[InferenceEngine] Window count: ",
    "[推理引擎] 大图像分块推理失败: ": "[InferenceEngine] Large image tile inference failed: ",
    "[推理引擎] 🛑 收到取消请求": "[InferenceEngine] 🛑 Cancellation request received",
    "[推理引擎] 🚀 开始大图像分块推理...": "[InferenceEngine] 🚀 Start large image tile inference...",
    "[推理引擎] 进度: ": "[InferenceEngine] Progress: ",
    "[推理引擎] 分块预测完成，耗时: ": "[InferenceEngine] Tile prediction complete, time: ",
    ") 推理失败: ": ") inference failed: ",
    "[推理引擎] 🛑 分块推理已取消": "[InferenceEngine] 🛑 Tile inference cancelled",
    "[推理引擎] ⚠️  模型加载失败，使用模拟模式": "[InferenceEngine] ⚠️  Model load failed, using mock mode",
    "[推理引擎] 使用全图缩放推理": "[InferenceEngine] Using full image scale inference",
    "[推理引擎] ✅ 大图像分块推理完成！": "[InferenceEngine] ✅ Large image tile inference complete!",
    "[推理引擎] 滑窗推理失败: ": "[InferenceEngine] Sliding window inference failed: ",
    "图像文件不存在: ": "Image file not found: ",
    "[推理引擎] 正在为输出结果构建金字塔...": "[InferenceEngine] Building pyramid for output results...",
    "[推理引擎] 输出文件: ": "[InferenceEngine] Output file: ",
    "[推理引擎] 🛑 拼接已取消": "[InferenceEngine] 🛑 Stitching cancelled",
    "[推理引擎] 开始拼接分块结果...": "[InferenceEngine] Start stitching tile results...",
    "\\n\\n详细信息:\\n": "\\n\\nDetailed info:\\n",

    # logic_engine.py
    "=== 测试扁平数据结构（向后兼容）===": "=== Test Flat Data Structure ===",
    "❌ 配置校验失败:": "❌ Config validation failed:",
    "✅ 配置校验通过": "✅ Config validation passed",
    "学习率 (Learning Rate) 必须大于 0。": "Learning Rate must be greater than 0.",
    ") 必须是 32 的倍数 (如 256, 512, 1024)，否则模型无法推理。": ") must be a multiple of 32 (e.g. 256, 512, 1024), otherwise inference will fail.",
    "=== 测试嵌套数据结构 ===": "=== Test Nested Data Structure ===",
    "✅ 配置文件已生成: ": "✅ Config file generated: ",

    # mask_renderer.py
    "mask必须是2D数组,当前维度: ": "mask must be 2D array, current dim: ",
    "image必须是3通道RGB图像,当前形状: ": "image must be 3 channel RGB, current shape: ",
    "colored_mask必须是3通道RGB图像,当前形状: ": "colored_mask must be 3 channel RGB, current shape: ",

    # project_manager.py
    "未设置": "Not Set",
    "模型配置文件": "Model Config File",
    "不存在: ": "Not Found: ",
    "自定义模块目录不存在: ": "Custom module dir not found: ",
    "数据集根目录": "Dataset Root Dir",
    "模型权重文件": "Model Weight File",

    # thumbnail_manager.py
    "⚠️ 缩略图加载失败 [": "⚠️ Thumbnail load failed [",
    "⚠️ 无法创建缓存目录: ": "⚠️ Cannot create cache directory: ",
    "⚠️ 保存缩略图缓存失败 [": "⚠️ Save thumbnail cache failed [",
    "📁 缩略图缓存目录: ": "📁 Thumbnail cache dir: ",

    # training_dispatcher.py
    "文件未找到: ": "File not found: ",
    "运行时错误: ": "Runtime error: ",
    "未知错误: ": "Unknown error: ",
    "训练进程启动失败：无法获取进程对象": "Training process start failed: unable to get process object",

    # framework_adapters/mmseg_trainer.py
    "[Warning] 这可能导致 mmdet 等依赖无法导入，请确保在 Conda 环境中运行 GUI 或显式指定 python_path。": "[Warning] This may cause mmdet dependency issues. Please run GUI in Conda or specify python_path.",
    "[Warning] CONDA_PREFIX 存在但未找到 python，回退到 ": "[Warning] CONDA_PREFIX exists but python not found, fallback to ",
    "基础配置文件不存在: ": "Base config not found: ",
    "找不到 MMSeg 训练脚本(train.py)。请确保已在目标 conda 环境中正确安装 mmsegmentation。": "Cannot find MMSeg train.py. Ensure mmsegmentation is installed in target conda env.",
    "训练进程已在运行，请先停止当前训练": "Training process already running, please stop it first",
    "[INFO] 使用 Conda 环境 Python: ": "[INFO] Using Conda Python: ",
    "mmengine 未安装。请运行: pip install mmengine": "mmengine not installed. Please run: pip install mmengine",
    "配置文件不存在: ": "Config file not found: ",
    "[Warning] 未指定 python_path 且未检测到 CONDA_PREFIX，使用打包解释器 ": "[Warning] python_path not specified and no CONDA_PREFIX, using packaged interpreter ",
    "无法加载框架 '": "Cannot load framework '",

    # utils/env_check_worker.py
    "探针输出解析失败: ": "Probe output parse failed: ",
    "探针超时（>15s），解释器响应过慢": "Probe timeout (>15s), interpreter response too slow",
    "解释器执行失败: ": "Interpreter execution failed: ",
    ". 原始输出: ": ". Raw output: ",
    "探针无输出": "Probe has no output",
    "Python 路径不存在: ": "Python path not found: ",
    "探针异常: ": "Probe exception: ",
    " (需要 ": " (Needs ",
    " 版本不兼容: ": " Version incompatible: ",
    "\\n请运行: pip install ": "\\nPlease run: pip install ",
    
    # utils/pyramid_builder.py
    "金字塔已存在": "Pyramid already exists",
    "GDAL 未安装": "GDAL not installed",
    "检查金字塔失败: ": "Check pyramid failed: ",
    "文件不存在: ": "File not found: ",
    "检测到无金字塔，开始构建...": "No pyramid detected, starting build...",
    "构建金字塔失败: ": "Pyramid build failed: ",
    "获取金字塔信息失败: ": "Get pyramid info failed: ",
    
    # core/config_parser.py
    "配置文件解析失败: ": "Config parse failed: ",
    "类别和调色板解析警告: ": "Classes and palette parse warning: ",
}

for directory in directories:
    if not os.path.exists(directory):
        continue
    for root, _, files in os.walk(directory):
        for filename in files:
            if filename.endswith('.py'):
                file_path = os.path.join(root, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                changed = False
                for k, v in replacements.items():
                    if k in content:
                        content = content.replace(k, v)
                        changed = True

                if changed:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"Updated {file_path}")

print("Replacement Phase 4 complete.")
