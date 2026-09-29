# -*- coding: utf-8 -*-
"""
Phase 2 单元测试：核心逻辑层

测试 ConfigAdvisor.recommend_rs_params() 和 TrainingThread 信号机制。
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys
import os

from core.config_advisor import DatasetInsights, ConfigAdvisor


# ========== Task 2.1: recommend_rs_params 测试 ==========

class TestRecommendRsParams:
    """ConfigAdvisor.recommend_rs_params() 测试"""

    def test_default_in_channels(self):
        """默认通道数为 3"""
        insights = DatasetInsights()
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert params['in_channels'] == 3

    def test_multispectral_in_channels(self):
        """遥感多光谱通道数"""
        insights = DatasetInsights(num_channels=8)
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert params['in_channels'] == 8

    def test_crop_size_returned(self):
        """推荐 crop_size 是元组"""
        insights = DatasetInsights(
            min_size=(800, 600),
            max_size=(1200, 900)
        )
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert isinstance(params['crop_size'], tuple)
        assert len(params['crop_size']) == 2
        assert params['crop_size'][0] > 0

    def test_class_weight_empty(self):
        """无类别时权重为空列表"""
        insights = DatasetInsights()
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert params['class_weight'] == []

    def test_class_weight_sorted(self):
        """类别权重按 class_id 排序"""
        insights = DatasetInsights(
            pixel_ratios={'2': 0.3, '0': 0.5, '1': 0.2},
            suggested_class_weights={'2': 1.5, '0': 0.8, '1': 2.0}
        )
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        # 应按 0, 1, 2 排序
        assert params['class_weight'] == [0.8, 2.0, 1.5]

    def test_loss_config_included(self):
        """包含损失函数配置"""
        insights = DatasetInsights()
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert 'loss_config' in params
        assert 'type' in params['loss_config']

    def test_augmentation_included(self):
        """包含数据增强配置"""
        insights = DatasetInsights()
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert 'augmentation' in params
        assert 'augmentations' in params['augmentation']

    def test_imbalanced_dataset_focal_loss(self):
        """不平衡数据集 + 小目标 → FocalLoss"""
        insights = DatasetInsights(
            pixel_ratios={'0': 0.95, '1': 0.005, '2': 0.045},
            suggested_class_weights={'0': 0.1, '1': 20.0, '2': 1.0},
            small_object_ratio=0.5,
        )
        advisor = ConfigAdvisor(insights)
        params = advisor.recommend_rs_params()
        assert params['loss_config']['type'] == 'FocalLoss'


# ========== DatasetInsights 新字段测试 ==========

class TestDatasetInsightsNewFields:
    """DatasetInsights 新增字段测试"""

    def test_avg_size_default(self):
        """avg_size 默认值"""
        ins = DatasetInsights()
        assert ins.avg_size == (0, 0)

    def test_num_channels_default(self):
        """num_channels 默认值"""
        ins = DatasetInsights()
        assert ins.num_channels == 3

    def test_num_channels_custom(self):
        """自定义通道数"""
        ins = DatasetInsights(num_channels=4)
        assert ins.num_channels == 4

    def test_avg_size_custom(self):
        """自定义平均尺寸"""
        ins = DatasetInsights(avg_size=(1024, 768))
        assert ins.avg_size == (1024, 768)


# ========== Task 2.2: TrainingThread 测试 ==========

class TestTrainingThread:
    """TrainingThread 测试（mock 训练器）"""

    @pytest.fixture
    def mock_trainer(self):
        trainer = MagicMock(spec=['start_training', 'stop_training',
                                  'parse_log_line', 'is_running',
                                  'get_process'])
        trainer.is_running.return_value = False
        return trainer

    def test_import(self):
        """TrainingThread 可以导入"""
        from core.training_dispatcher import TrainingThread
        assert TrainingThread is not None

    def test_init(self, mock_trainer):
        """初始化不报错"""
        from core.training_dispatcher import TrainingThread
        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )
        assert thread.trainer is mock_trainer

    def test_stop_sets_flag(self, mock_trainer):
        """stop() 调用 trainer.stop_training"""
        from core.training_dispatcher import TrainingThread
        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )
        thread.stop()
        mock_trainer.stop_training.assert_called_once()

    def test_signals_exist(self, mock_trainer):
        """所有信号均已定义"""
        from core.training_dispatcher import TrainingThread
        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )
        # 验证信号对象存在（PySide6 Signal 是 descriptor）
        assert hasattr(thread, 'log_parsed')
        assert hasattr(thread, 'log_raw')
        assert hasattr(thread, 'training_finished')
        assert hasattr(thread, 'training_error')
        assert hasattr(thread, 'progress_updated')

    def test_run_with_no_process(self, mock_trainer):
        """get_process 返回 None 时发射错误信号"""
        from core.training_dispatcher import TrainingThread
        mock_trainer.get_process.return_value = None

        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )

        # 收集信号
        errors = []
        finished_codes = []
        thread.training_error.connect(errors.append)
        thread.training_finished.connect(finished_codes.append)

        thread.run()  # 直接调用 run（不启动线程）

        mock_trainer.start_training.assert_called_once()
        assert len(errors) == 1
        assert 'Training process start failed' in errors[0]
        assert finished_codes == [-1]

    def test_run_reads_stdout(self, mock_trainer):
        """正常运行：读取 stdout 并解析日志"""
        from core.training_dispatcher import TrainingThread

        # 模拟进程 stdout
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Iter(train) [1/100]  lr: 0.01  loss: 0.5\n",
            "Iter(train) [2/100]  lr: 0.01  loss: 0.4\n",
            "",  # 空行终止
        ]
        mock_proc.wait.return_value = 0
        mock_trainer.get_process.return_value = mock_proc
        mock_trainer.parse_log_line.side_effect = [
            {'type': 'train_loss', 'iter': 1, 'max_iter': 100, 'loss': 0.5},
            {'type': 'train_loss', 'iter': 2, 'max_iter': 100, 'loss': 0.4},
        ]

        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )

        raw_lines = []
        parsed_logs = []
        progress = []
        finished_codes = []
        thread.log_raw.connect(raw_lines.append)
        thread.log_parsed.connect(parsed_logs.append)
        thread.progress_updated.connect(lambda cur, mx: progress.append((cur, mx)))
        thread.training_finished.connect(finished_codes.append)

        thread.run()

        assert len(raw_lines) == 2
        assert len(parsed_logs) == 2
        assert parsed_logs[0]['loss'] == 0.5
        assert progress == [(1, 100), (2, 100)]
        assert finished_codes == [0]

    def test_run_handles_exception(self, mock_trainer):
        """start_training 抛异常时发射错误信号"""
        from core.training_dispatcher import TrainingThread
        mock_trainer.start_training.side_effect = FileNotFoundError("config not found")

        thread = TrainingThread(
            trainer=mock_trainer,
            config_path='/fake/config.py',
            work_dir='/fake/work_dir'
        )

        errors = []
        finished_codes = []
        thread.training_error.connect(errors.append)
        thread.training_finished.connect(finished_codes.append)

        thread.run()

        assert len(errors) == 1
        assert 'config not found' in errors[0]
        assert finished_codes == [-1]
