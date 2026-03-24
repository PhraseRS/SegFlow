# -*- coding: utf-8 -*-
"""通用 UI 组件"""

from ui.widgets.ui_utils import (
    create_flat_button,
    create_header_action_button,
    create_toolbar_separator,
    create_qta_icon,
    ICON_COLORS,
    HAS_QTAWESOME
)

from ui.widgets.collapsible_widget import (
    CollapsiblePanel,
    CollapsibleContainer
)

from ui.widgets.dataset_overview_widget import DatasetOverviewWidget
from ui.widgets.health_check_widget import HealthCheckCard
from ui.widgets.class_distribution_widget import ClassDistributionWidget
from ui.widgets.task_config_dashboard import TaskConfigDashboard

from ui.widgets.layer_manager import (
    LayerManager,
    LayerSlot,
    TaskGroup,
    SlotType,
    ZOrder,
    create_layer_manager
)

__all__ = [
    # UI Utils
    'create_flat_button',
    'create_header_action_button',
    'create_toolbar_separator',
    'create_qta_icon',
    'ICON_COLORS',
    'HAS_QTAWESOME',
    # Collapsible
    'CollapsiblePanel',
    'CollapsibleContainer',
    # Widgets
    'DatasetOverviewWidget',
    'HealthCheckCard',
    'ClassDistributionWidget',
    'TaskConfigDashboard',
    # Layer Manager
    'LayerManager',
    'LayerSlot',
    'TaskGroup',
    'SlotType',
    'ZOrder',
    'create_layer_manager',
]

