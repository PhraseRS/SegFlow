# -*- coding: utf-8 -*-
"""
框架注册表 (Framework Registry)

以数据驱动方式描述每个深度学习框架的元数据，
避免在 UI 和工具类中硬编码框架名称与探针包列表。

使用方式：
    from core.framework_registry import FRAMEWORK_REGISTRY, get_framework_spec

    spec = get_framework_spec("mmseg")
    print(spec.display_name)          # "MMSegmentation"
    print(spec.required_packages)     # ["torch", "mmcv", "mmseg"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type


@dataclass
class FrameworkSpec:
    """
    单个框架的元数据描述。

    Attributes:
        key:               内部唯一标识，如 "mmseg"
        display_name:      UI 显示名称，如 "MMSegmentation"
        required_packages: 环境探针需要检测的包列表
        trainer_class_path: 训练器类的完整导入路径（字符串，延迟导入避免循环依赖）
        description:       简短说明（用于 tooltip 等）
        version_constraints: 包版本约束，如 {"mmseg": ">=1.0.0,<2.0.0"}
    """
    key: str
    display_name: str
    required_packages: List[str]
    trainer_class_path: str
    description: str = ""
    version_constraints: Dict[str, str] = field(default_factory=dict)

    def load_trainer_class(self) -> Type:
        """
        按需导入并返回对应的 Trainer 类。
        延迟导入避免循环依赖，同时在框架未安装时给出清晰错误。
        """
        module_path, class_name = self.trainer_class_path.rsplit(".", 1)
        import importlib
        try:
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"无法加载框架 '{self.display_name}' 的训练器 "
                f"'{self.trainer_class_path}': {e}"
            ) from e


# ---------------------------------------------------------------------------
# 注册表：所有已支持的框架
# ---------------------------------------------------------------------------

FRAMEWORK_REGISTRY: Dict[str, FrameworkSpec] = {
    "mmseg": FrameworkSpec(
        key="mmseg",
        display_name="MMSegmentation",
        required_packages=["torch", "mmcv", "mmseg"],
        trainer_class_path="core.framework_adapters.mmseg_trainer.MMSegTrainer",
        description="OpenMMLab 语义分割框架，支持 SegFormer、UperNet 等主流算法",
        version_constraints={
            "mmseg": ">=1.0.0,<2.0.0",
            "mmcv": ">=2.0.0",
            "mmengine": ">=0.7.0",
        },
    ),
    # 未来扩展示例（注释保留，方便后续接入）：
    # "paddleseg": FrameworkSpec(
    #     key="paddleseg",
    #     display_name="PaddleSeg",
    #     required_packages=["paddle", "paddleseg"],
    #     trainer_class_path="core.framework_adapters.paddleseg_trainer.PaddleSegTrainer",
    #     description="百度飞桨语义分割框架",
    # ),
}


# ---------------------------------------------------------------------------
# 便捷访问函数
# ---------------------------------------------------------------------------

def get_framework_spec(key: str) -> Optional[FrameworkSpec]:
    """按 key 获取框架规格，不存在时返回 None。"""
    return FRAMEWORK_REGISTRY.get(key)


def get_all_display_names() -> List[str]:
    """返回所有已注册框架的显示名称列表（用于 ComboBox）。"""
    return [spec.display_name for spec in FRAMEWORK_REGISTRY.values()]


def get_key_by_display_name(display_name: str) -> Optional[str]:
    """根据显示名称反查 key。"""
    for key, spec in FRAMEWORK_REGISTRY.items():
        if spec.display_name == display_name:
            return key
    return None


def get_required_packages(display_name: str) -> List[str]:
    """根据显示名称获取所需包列表，未找到时返回空列表。"""
    key = get_key_by_display_name(display_name)
    if key is None:
        return []
    return FRAMEWORK_REGISTRY[key].required_packages



def get_version_constraints(display_name: str) -> Dict[str, str]:
    """根据显示名称获取版本约束字典，未找到时返回空字典。"""
    key = get_key_by_display_name(display_name)
    if key is None:
        return {}
    return FRAMEWORK_REGISTRY[key].version_constraints
