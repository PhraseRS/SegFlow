# -*- coding: utf-8 -*-
"""
UI 工具函数 (UI Utilities)
提供统一风格的 UI 组件工厂方法

关键约束：禁止使用 CSS/QSS (setStyleSheet)
必须通过 Qt 原生组件属性或 qtawesome 来实现样式控制
"""

from typing import Optional, Callable, Dict, Any
from PySide6.QtWidgets import QToolButton, QWidget, QFrame, QSizePolicy
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QColor

# 尝试导入 qtawesome，如果不可用则使用 fallback
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    print("⚠️ qtawesome 未安装，将使用文本替代图标")


# ==================== 图标颜色预设 ====================
ICON_COLORS = {
    'default': '#666666',      # 默认灰色
    'primary': '#2196F3',      # 主色调蓝色
    'success': '#4CAF50',      # 成功绿色
    'warning': '#FF9800',      # 警告橙色
    'danger': '#F44336',       # 危险红色
    'muted': '#9E9E9E',        # 弱化灰色
}


def create_qta_icon(
    icon_name: str,
    color: str = 'default',
    size: int = 16
) -> Optional[QIcon]:
    """
    使用 qtawesome 创建图标
    
    Args:
        icon_name: 图标名称，如 'fa5s.sync-alt'
        color: 颜色名称（预设）或十六进制颜色值
        size: 图标尺寸
    
    Returns:
        QIcon 或 None（如果 qtawesome 不可用）
    """
    if not HAS_QTAWESOME:
        return None
    
    # 解析颜色
    if color in ICON_COLORS:
        color_value = ICON_COLORS[color]
    else:
        color_value = color
    
    try:
        return qta.icon(icon_name, color=color_value)
    except Exception as e:
        print(f"⚠️ 创建图标失败 ({icon_name}): {e}")
        return None


def create_flat_button(
    text: str = "",
    icon_name: Optional[str] = None,
    icon_color: str = 'default',
    tooltip: str = "",
    parent: Optional[QWidget] = None,
    on_clicked: Optional[Callable] = None,
    checkable: bool = False,
    enabled: bool = True
) -> QToolButton:
    """
    创建统一风格的扁平按钮（无边框，autoRaise 效果）
    
    关键特性：
    - 使用 QToolButton + setAutoRaise(True) 实现扁平效果
    - 不使用 setStyleSheet，完全依赖原生属性
    - 图标通过 qtawesome 加载
    
    Args:
        text: 按钮文字
        icon_name: qtawesome 图标名称，如 'fa5s.sync-alt'
        icon_color: 图标颜色（预设名或十六进制）
        tooltip: 工具提示
        parent: 父控件
        on_clicked: 点击回调函数
        checkable: 是否可切换状态
        enabled: 是否启用
    
    Returns:
        QToolButton: 配置好的扁平按钮
    """
    btn = QToolButton(parent)
    
    # 核心：设置 autoRaise 实现扁平效果
    btn.setAutoRaise(True)
    
    # 设置文字
    if text:
        btn.setText(text)
    
    # 设置图标
    if icon_name:
        icon = create_qta_icon(icon_name, icon_color)
        if icon:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
            # 图标在左，文字在右
            if text:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            else:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    
    # 设置工具提示
    if tooltip:
        btn.setToolTip(tooltip)
    
    # 设置光标
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    
    # 设置可切换状态
    btn.setCheckable(checkable)
    
    # 设置启用状态
    btn.setEnabled(enabled)
    
    # 连接点击信号
    if on_clicked:
        btn.clicked.connect(on_clicked)
    
    return btn


def create_header_action_button(
    text: str = "",
    icon_name: Optional[str] = None,
    icon_color: str = 'default',
    tooltip: str = "",
    parent: Optional[QWidget] = None,
    on_clicked: Optional[Callable] = None
) -> QToolButton:
    """
    创建用于折叠面板 Header 的操作按钮
    
    与 create_flat_button 类似，但针对 Header 区域优化：
    - 更紧凑的尺寸
    - 适合放在标题栏右侧
    
    Args:
        text: 按钮文字
        icon_name: qtawesome 图标名称
        icon_color: 图标颜色
        tooltip: 工具提示
        parent: 父控件
        on_clicked: 点击回调
    
    Returns:
        QToolButton: 配置好的 Header 操作按钮
    """
    btn = create_flat_button(
        text=text,
        icon_name=icon_name,
        icon_color=icon_color,
        tooltip=tooltip,
        parent=parent,
        on_clicked=on_clicked
    )
    
    # Header 按钮的额外配置
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 不获取焦点，避免干扰
    
    return btn


def create_toolbar_separator(parent: Optional[QWidget] = None) -> QFrame:
    """
    创建工具栏分隔线（垂直线）
    
    Args:
        parent: 父控件
    
    Returns:
        QFrame: 垂直分隔线
    """
    separator = QFrame(parent)
    separator.setFrameShape(QFrame.Shape.VLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)
    separator.setFixedWidth(2)
    separator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    return separator
