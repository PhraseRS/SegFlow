---
name: pyside6-ui-development-rules
description: PySide6 desktop GUI development rules -- Signal/Slot architecture, QSS theming, QThread concurrency, layout management, and cross-platform rendering. Enforces MVC separation and responsive UI patterns.
version: 2.1.0
category: Languages
agents: [python-pro, developer]
tags: [pyside6, python, gui, desktop, qt, ui, signals-slots, qss, qthread]
model: sonnet
invoked_by: both
user_invocable: true
tools: [Read, Write, Edit, Bash, Glob, Grep]
globs: ['**/ui/**/*.*', '**/*_ui.py', '**/*_dialog.py', '**/*_window.py', '**/*_widget.py']
best_practices:
  - Use Qt Signal/Slot mechanism for all UI-to-logic communication
  - Never block the main thread with long-running operations
  - Apply QSS stylesheets at the QApplication level for consistent theming
  - Use layout managers instead of absolute pixel coordinates
  - Use @Slot decorator on slot methods for type safety and performance
  - Test on all target platforms before release
error_handling: graceful
streaming: supported
verified: true
lastVerifiedAt: '2026-05-08'
source: builtin
trust_score: 100
provenance_sha: aab9454f75a64219
---

# PySide6 UI Development Rules Skill

<identity>
PySide6 desktop GUI development specialist enforcing MVC separation, Signal/Slot architecture, QSS theming, threaded concurrency, and cross-platform rendering best practices. Ensures responsive, accessible, and visually consistent desktop applications.
</identity>

<capabilities>
- Design MVC-separated PySide6 application architecture
- Implement Signal/Slot communication patterns between UI and business logic
- Configure QSS application-level theming with dark/light mode support
- Manage background operations with QThread, QRunnable, and QThreadPool
- Build responsive layouts using QVBoxLayout, QHBoxLayout, QGridLayout, and QFormLayout
- Implement custom QWidget subclasses with proper paintEvent handling
- Set up cross-platform DPI-aware rendering
- Configure accessibility features (screen reader support, keyboard navigation)
</capabilities>

## Overview

This skill enforces rules for building production-quality PySide6 desktop applications. The core principles are: strict MVC separation via Signal/Slot, never blocking the UI thread, centralized theming via QSS, and layout-manager-driven responsive design. These rules prevent the most common Qt failures: frozen UIs, untestable coupling, and platform-specific rendering bugs.

## When to Use

- When building new PySide6 desktop applications
- When refactoring existing Qt UI code
- When debugging frozen or unresponsive Qt UIs
- When implementing custom widgets or complex layouts
- When setting up cross-platform desktop application builds

## Iron Laws

1. **ALWAYS** use Qt's Signal/Slot mechanism for UI-to-logic communication -- direct method calls between UI and business logic layers break MVC separation and cause untestable coupling.
2. **NEVER** perform long-running operations on the main UI thread -- blocking the Qt event loop makes the interface unresponsive and triggers OS "not responding" dialogs.
3. **ALWAYS** apply QSS stylesheets at the QApplication level rather than per-widget -- per-widget inline styles create inconsistent themes and unmaintainable styling sprawl.
4. **NEVER** use absolute pixel coordinates for widget layout -- use Qt layout managers (QVBoxLayout, QHBoxLayout, QGridLayout) to ensure DPI-aware and cross-platform rendering.
5. **ALWAYS** use `@Slot()` decorator on slot methods -- PySide6 requires explicit Slot decoration for proper type checking and cross-thread signal delivery.
6. **ALWAYS** test the UI on all target platforms before release -- PySide6 rendering, font scaling, and widget sizing differ between Windows, macOS, and Linux.

## Anti-Patterns

| Anti-Pattern                                   | Why It Fails                                                                      | Correct Approach                                                                      |
| ---------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Calling business logic directly from UI slots  | Couples UI to logic; makes testing impossible and breaks MVC architecture         | Emit signals from UI; connect to controller/service methods via slot                  |
| Running network or file I/O on the main thread | Blocks the Qt event loop; UI freezes until operation completes                    | Use QThread, QRunnable, or asyncio with qasync for background operations              |
| Hardcoding pixel sizes and positions           | Breaks on high-DPI displays and different OS DPI scaling settings                 | Use layout managers and size policies; use `logicalDpiX()` for DPI-aware sizing       |
| Setting styles inline on individual widgets    | Creates visual inconsistency; extremely difficult to theme or maintain            | Define a single QSS stylesheet at QApplication level and use object names/classes     |
| Ignoring cross-platform rendering differences  | Widget sizes, fonts, and margins differ significantly between Windows/macOS/Linux | Test on all target platforms; use platform-conditional logic where rendering diverges |

## Workflow

### Step 1: Application Architecture (MVC)

```python
# model.py -- Business logic, no Qt dependencies
class DataModel:
    def __init__(self):
        self._items = []

    def add_item(self, item: str) -> bool:
        if item and item not in self._items:
            self._items.append(item)
            return True
        return False

# controller.py -- Mediates between Model and View
from PySide6.QtCore import QObject, Signal, Slot

class Controller(QObject):
    items_changed = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, model: DataModel):
        super().__init__()
        self._model = model

    @Slot(str)
    def add_item(self, item: str) -> None:
        if self._model.add_item(item):
            self.items_changed.emit(self._model._items.copy())
        else:
            self.error_occurred.emit(f"Could not add: {item}")
```

### Step 2: Signal/Slot Wiring

```python
# view.py -- UI only, connects via signals/slots
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton, QListWidget

class MainView(QMainWindow):
    def __init__(self, controller: Controller):
        super().__init__()
        self._controller = controller

        # Wire signals to slots
        self._controller.items_changed.connect(self._on_items_changed)
        self._controller.error_occurred.connect(self._on_error)

        # UI emits to controller -- never calls model directly
        self._add_btn.clicked.connect(lambda: self._controller.add_item(self._input.text()))

    @Slot(list)
    def _on_items_changed(self, items: list) -> None:
        self._list.clear()
        self._list.addItems(items)
```

### Step 3: Background Operations

```python
from PySide6.QtCore import QThread, Signal, Slot

class WorkerThread(QThread):
    progress = Signal(int)
    finished_with_result = Signal(object)
    error = Signal(str)

    def __init__(self, task_fn, parent=None):
        super().__init__(parent)
        self._task_fn = task_fn

    def run(self):
        try:
            result = self._task_fn(self.progress.emit)
            self.finished_with_result.emit(result)
        except Exception as e:
            self.error.emit(str(e))
```

### Step 4: QSS Theming

```python
# Apply at QApplication level
app = QApplication(sys.argv)
app.setStyleSheet(Path("styles/dark-theme.qss").read_text())

# QSS file
"""
QMainWindow {
    background-color: #2b2b2b;
    color: #e0e0e0;
}
QPushButton {
    background-color: #3c3f41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 16px;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #4c5052;
}
"""
```

### Step 5: Layout Management

```python
# Use layout managers -- never setGeometry() or move()
layout = QVBoxLayout()
layout.addWidget(self._toolbar)
layout.addWidget(self._content, stretch=1)  # stretch fills available space
layout.addWidget(self._status_bar)

# For responsive grids
grid = QGridLayout()
grid.addWidget(label, 0, 0)
grid.addWidget(input_field, 0, 1)
grid.setColumnStretch(1, 1)  # input stretches, label stays fixed
```

## PySide6 Specific Notes

### Signal/Slot API Differences (vs PyQt6)

| PySide6 | PyQt6 Equivalent | Notes |
|---------|-------------------|-------|
| `Signal(int)` | `pyqtSignal(int)` | 类级别声明，不可在 `__init__` 中定义 |
| `@Slot(str)` | `@pyqtSlot(str)` | PySide6 中建议始终使用装饰器 |
| `Property(type, fget, fset)` | `pyqtProperty(type, fget, fset)` | QML 集成时使用 |
| `Signal` 支持 `str` 类型名 | 不支持 | PySide6 可用 `Signal("QVariantList")` |

### PySide6 特有注意事项

1. **snake_case 方法名**：PySide6 6.5+ 支持 `set_style_sheet()` 等 snake_case 别名，但本项目统一使用 camelCase（`setStyleSheet()`）以保持与 Qt C++ 文档一致。
2. **枚举作用域**：PySide6 同时支持 `Qt.AlignCenter` (旧) 和 `Qt.AlignmentFlag.AlignCenter` (新)。本项目统一使用完整作用域写法。
3. **`__feature__` 导入**：PySide6 支持 `from __feature__ import snake_case, true_property`，但不建议在本项目中使用，避免与第三方库冲突。
4. **对象所有权**：PySide6 的垃圾回收与 PyQt6 不同——Python 对象被 GC 回收后，底层 C++ 对象也会被销毁。务必为长生命周期的 QObject 设置 parent 或保持 Python 引用。
5. **多线程信号**：跨线程 emit Signal 时，PySide6 默认使用 `Qt.AutoConnection`（自动判断队列连接），但 slot 方法必须用 `@Slot()` 装饰才能保证类型安全的跨线程投递。

### Anti-Pattern: PySide6 对象生命周期陷阱

```python
# ❌ 错误：局部变量被 GC 回收，C++ 对象随之销毁
def create_timer():
    timer = QTimer()
    timer.timeout.connect(some_func)
    timer.start(1000)
    # timer 离开作用域后被回收，定时器失效

# ✅ 正确：保持引用或设置 parent
def create_timer(self):
    self._timer = QTimer(self)  # parent=self 或 self._timer 保持引用
    self._timer.timeout.connect(some_func)
    self._timer.start(1000)
```

## Complementary Skills

| Skill                   | Relationship                                            |
| ----------------------- | ------------------------------------------------------- |
| `modern-python`         | Project setup with uv, ruff, ty, pytest                 |
| `python-backend-expert` | Backend service patterns for desktop app backends       |
| `tdd`                   | Test-driven development for Qt widget testing           |
| `accessibility`         | Accessibility audit patterns applicable to desktop apps |

## Memory Protocol (MANDATORY)

**Before starting:**

Read `.claude/context/memory/learnings.md` for prior PySide6 patterns and platform-specific workarounds.

**After completing:** Record any platform-specific rendering issues, Signal/Slot patterns, or QThread gotchas to `.claude/context/memory/learnings.md`.

> ASSUME INTERRUPTION: Your context may reset. If it's not in memory, it didn't happen.
