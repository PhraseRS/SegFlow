# -*- coding: utf-8 -*-
"""
WheelGuard — 通用滚轮事件拦截器

适用于 QSpinBox / QDoubleSpinBox / QComboBox / QAbstractSlider 等
默认在未获焦点状态下也接收滚轮事件的输入控件，避免在 QScrollArea 内
鼠标悬停误改参数。

设计：
- 仅当控件已获得键盘焦点时允许滚轮事件按 Qt 默认逻辑处理
- 否则在事件过滤器中 ignore() + 返回 True，让 Qt 把事件冒泡给最近的
  QScrollArea，从而触发面板滚动
- 同时把目标控件焦点策略调整为 Qt.StrongFocus（点击 / Tab 才获焦），
  保留键盘 ↑↓ 调值能力，禁止 hover 即获焦的滚轮调值
"""

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QAbstractSlider


class WheelGuard(QObject):
    """事件过滤器：未获焦点的目标控件吞掉自身滚轮事件并交还父级。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            # 未获键盘焦点 → 拒绝滚轮事件，让 QScrollArea 接管
            try:
                has_focus = obj.hasFocus()
            except Exception:
                has_focus = False
            if not has_focus:
                event.ignore()
                return True   # 拦截，避免基类 wheelEvent 改写控件值
        return super().eventFilter(obj, event)


# 模块级单例：所有目标控件共享一个过滤器即可，节省对象数量
_GLOBAL_WHEEL_GUARD = WheelGuard()


# 受保护的控件类型
_GUARDED_TYPES = (QAbstractSpinBox, QComboBox, QAbstractSlider)


def install_wheel_guard(root_widget) -> int:
    """
    递归遍历 root_widget 下所有子控件，
    为 SpinBox / ComboBox / Slider 类批量安装事件过滤器。

    Args:
        root_widget: 任何 QWidget 子类。若为 None 则直接返回 0。

    Returns:
        实际安装的控件数量（便于调试 / 日志）。
    """
    if root_widget is None:
        return 0

    count = 0
    # findChildren 在传入 tuple 时 PySide6 不支持，改为分别查找后合并
    children = []
    for cls in _GUARDED_TYPES:
        children.extend(root_widget.findChildren(cls))

    # 同一个控件可能多次匹配（多继承场景）；用 id 去重
    seen = set()
    for child in children:
        key = id(child)
        if key in seen:
            continue
        seen.add(key)

        # StrongFocus：点击 / Tab 可获焦，hover 不获焦 → 完美契合需求
        child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        child.installEventFilter(_GLOBAL_WHEEL_GUARD)
        count += 1

    return count
