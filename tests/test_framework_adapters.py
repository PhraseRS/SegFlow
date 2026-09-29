# -*- coding: utf-8 -*-
"""
Phase 1 单元测试：框架适配层

测试 BaseTrainer 接口规范和 MMSegTrainer 的日志解析、进程管理逻辑。
配置生成需要 mmengine，因此 mock 处理。
"""

import os
import subprocess
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from core.framework_adapters.base_trainer import BaseTrainer
from core.framework_adapters.mmseg_trainer import MMSegTrainer


# ========== BaseTrainer 测试 ==========

class TestBaseTrainer:
    """验证 BaseTrainer 是真正的抽象类，不能直接实例化"""

    def test_cannot_instantiate_abstract_class(self):
        """BaseTrainer 不能直接实例化"""
        with pytest.raises(TypeError):
            BaseTrainer()

    def test_concrete_subclass_must_implement_all_methods(self):
        """只实现部分方法的子类不能实例化"""
        class PartialTrainer(BaseTrainer):
            def generate_config(self, ui_params, advisor_params, save_path):
                pass
            # 缺少其他方法

        with pytest.raises(TypeError):
            PartialTrainer()

    def test_complete_subclass_can_instantiate(self):
        """实现全部方法的子类可以实例化"""
        class CompleteTrainer(BaseTrainer):
            def generate_config(self, ui_params, advisor_params, save_path):
                return save_path
            def start_training(self, config_path, work_dir):
                pass
            def stop_training(self):
                pass
            def parse_log_line(self, line):
                return None
            def is_running(self):
                return False
            def get_process(self):
                return None

        trainer = CompleteTrainer()
        assert trainer.is_running() is False
        assert trainer.get_process() is None


# ========== MMSegTrainer 日志解析测试 ==========

class TestMMSegTrainerLogParsing:
    """MMSegTrainer.parse_log_line 日志解析测试"""

    @pytest.fixture
    def trainer(self):
        return MMSegTrainer()

    def test_parse_train_log_standard(self, trainer):
        """解析标准训练日志行"""
        line = (
            "2024/01/15 10:30:00 - mmengine - INFO - "
            "Iter(train) [100/40000]  lr: 1.0000e-02  "
            "eta: 2:30:00  loss: 0.4567"
        )
        result = trainer.parse_log_line(line)
        assert result is not None
        assert result['type'] == 'train_loss'
        assert result['iter'] == 100
        assert result['max_iter'] == 40000
        assert result['lr'] == pytest.approx(0.01)
        assert result['loss'] == pytest.approx(0.4567)
        assert result['eta'] == '2:30:00'

    def test_parse_train_log_without_eta(self, trainer):
        """解析不含 ETA 的训练日志"""
        line = (
            "mmengine - INFO - Iter(train) [500/20000]  "
            "lr: 5.0e-04  loss: 0.2345"
        )
        result = trainer.parse_log_line(line)
        assert result is not None
        assert result['type'] == 'train_loss'
        assert result['iter'] == 500
        assert result['loss'] == pytest.approx(0.2345)
        assert 'eta' not in result

    def test_parse_val_log_miou(self, trainer):
        """解析验证指标日志（mIoU）"""
        line = (
            "2024/01/15 11:00:00 - mmengine - INFO - "
            "mIoU: 0.5678  mAcc: 0.7890"
        )
        result = trainer.parse_log_line(line)
        assert result is not None
        assert result['type'] == 'val_metric'
        assert result['mIoU'] == pytest.approx(0.5678)
        assert result['mAcc'] == pytest.approx(0.7890)

    def test_parse_val_log_miou_only(self, trainer):
        """解析只有 mIoU 的验证日志"""
        line = "INFO - mIoU: 0.4321"
        result = trainer.parse_log_line(line)
        assert result is not None
        assert result['type'] == 'val_metric'
        assert result['mIoU'] == pytest.approx(0.4321)
        assert 'mAcc' not in result

    def test_parse_unrelated_log(self, trainer):
        """无法解析的日志行返回 None"""
        line = "Loading checkpoint from epoch_10.pth..."
        result = trainer.parse_log_line(line)
        assert result is None

    def test_parse_empty_line(self, trainer):
        """空行返回 None"""
        assert trainer.parse_log_line("") is None
        assert trainer.parse_log_line("   ") is None
        assert trainer.parse_log_line(None) is None


# ========== MMSegTrainer 进程管理测试 ==========

class TestMMSegTrainerProcessManagement:
    """MMSegTrainer 进程管理测试（使用 mock）"""

    @pytest.fixture
    def trainer(self):
        return MMSegTrainer()

    def test_initial_state(self, trainer):
        """初始状态：无进程运行"""
        assert trainer.is_running() is False
        assert trainer.get_process() is None

    def test_start_training_file_not_found(self, trainer, tmp_path):
        """启动训练时配置文件不存在"""
        with pytest.raises(FileNotFoundError):
            trainer.start_training(
                str(tmp_path / "nonexistent.py"),
                str(tmp_path / "work_dir")
            )

    def test_start_training_creates_work_dir(self, trainer, tmp_path):
        """启动训练时自动创建工作目录"""
        config_path = tmp_path / "config.py"
        config_path.write_text("# test config")
        work_dir = tmp_path / "new_work_dir"

        # mock Popen 以及 mmengine/mmseg 模块以避免真正启动进程或因为环境未安装导致失败
        mock_mmseg = MagicMock()
        mock_mmseg.__file__ = "/mock/path/to/mmseg/__init__.py"
        with patch('core.framework_adapters.mmseg_trainer.subprocess.Popen') as mock_popen, \
             patch.dict('sys.modules', {'mmseg': mock_mmseg}), \
             patch('os.path.isfile', return_value=True):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None  # 进程运行中
            mock_popen.return_value = mock_proc

            trainer.start_training(str(config_path), str(work_dir))

            assert work_dir.exists()
            assert trainer.is_running() is True
            assert trainer.get_process() is mock_proc

    def test_cannot_start_while_running(self, trainer, tmp_path):
        """运行中不能再次启动"""
        config_path = tmp_path / "config.py"
        config_path.write_text("# test config")

        mock_mmseg = MagicMock()
        mock_mmseg.__file__ = "/mock/path/to/mmseg/__init__.py"
        with patch('core.framework_adapters.mmseg_trainer.subprocess.Popen') as mock_popen, \
             patch.dict('sys.modules', {'mmseg': mock_mmseg}), \
             patch('os.path.isfile', return_value=True):
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            trainer.start_training(str(config_path), str(tmp_path / "work"))

            with pytest.raises(RuntimeError, match="already running"):
                trainer.start_training(str(config_path), str(tmp_path / "work2"))

    def test_stop_training_graceful(self, trainer):
        """优雅停止训练"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # 运行中
        mock_proc.wait.return_value = 0
        trainer._process = mock_proc

        trainer.stop_training()

        assert trainer._process is None
        # 验证尝试了终止
        assert (mock_proc.terminate.called or mock_proc.send_signal.called)

    def test_stop_training_already_stopped(self, trainer):
        """停止已终止的进程不报错"""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # 已结束
        trainer._process = mock_proc

        trainer.stop_training()
        assert trainer._process is None

    def test_stop_training_no_process(self, trainer):
        """没有进程时停止不报错"""
        trainer.stop_training()  # 不应抛出异常


# ========== MMSegTrainer 配置生成测试 ==========

class TestMMSegTrainerConfigGeneration:
    """MMSegTrainer.generate_config 测试"""

    @pytest.fixture
    def trainer(self):
        return MMSegTrainer()

    def test_generate_config_no_mmengine(self, trainer, tmp_path):
        """mmengine 未安装时抛出 ImportError"""
        with patch.dict('sys.modules', {'mmengine': None, 'mmengine.config': None}):
            with pytest.raises(ImportError, match="mmengine"):
                trainer.generate_config(
                    ui_params={'base_config': 'some.py'},
                    advisor_params={},
                    save_path=str(tmp_path / "out.py")
                )

    def test_generate_config_base_not_found(self, trainer, tmp_path):
        """基础配置文件不存在"""
        # Mock mmengine 以通过 import 检查
        mock_config_module = MagicMock()
        with patch.dict('sys.modules', {
            'mmengine': MagicMock(),
            'mmengine.config': mock_config_module,
            'mmengine.config.config': MagicMock(),
            'mmengine.utils': MagicMock(),
            'mmengine.utils.misc': MagicMock(),
        }):
            with pytest.raises(FileNotFoundError, match="Not Found"):
                trainer.generate_config(
                    ui_params={'base_config': '/nonexistent/config.py'},
                    advisor_params={},
                    save_path=str(tmp_path / "out.py")
                )
