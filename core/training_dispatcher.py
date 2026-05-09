# -*- coding: utf-8 -*-
"""
训练任务调度器 (Training Dispatcher)

使用 PySide6 QThread 管理训练子进程，避免 UI 卡死。
持续读取子进程输出，解析日志，通过 Signal 实时发送给 UI 主线程。

Training Roadmap Phase 2, Task 2.2
"""

from PySide6.QtCore import QThread, Signal
from typing import Optional

from core.framework_adapters.base_trainer import BaseTrainer


class TrainingThread(QThread):
    """
    训练线程 — 在后台运行训练子进程并实时发射日志信号。

    Signals:
        log_parsed(dict): 解析后的结构化日志（loss/mIoU/lr/eta）
        log_raw(str): 原始日志行（供终端控制台显示）
        training_finished(int): 训练结束，携带退出码
        training_error(str): 训练异常消息
        progress_updated(int, int): (当前迭代, 总迭代) 进度信号
    """

    log_parsed = Signal(dict)
    log_raw = Signal(str)
    training_finished = Signal(int)
    training_error = Signal(str)
    progress_updated = Signal(int, int)
    live_prediction_updated = Signal(dict)

    def __init__(
        self,
        trainer: BaseTrainer,
        config_path: str,
        work_dir: str,
        python_path: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._trainer = trainer
        self._config_path = config_path
        self._work_dir = work_dir
        self._python_path = python_path   # 目标 conda 环境解释器路径
        self._should_stop = False

    def run(self):
        """
        线程主函数：启动训练并持续读取日志。
        """
        try:
            # 启动训练子进程（传递 python_path 以使用目标 conda 环境）
            self._trainer.start_training(
                self._config_path,
                self._work_dir,
                python_path=self._python_path,
            )

            process = self._trainer.get_process()
            if process is None:
                self.training_error.emit("训练进程启动失败：无法获取进程对象")
                self.training_finished.emit(-1)
                return

            # 持续读取 stdout
            for line in iter(process.stdout.readline, ''):
                if self._should_stop:
                    break

                line = line.rstrip('\n\r')
                if not line:
                    continue

                # 发射原始日志
                self.log_raw.emit(line)

                # 解析并发射结构化日志
                parsed = self._trainer.parse_log_line(line)
                if parsed:
                    self.log_parsed.emit(parsed)

                    if parsed.get('type') == 'live_prediction':
                        self.live_prediction_updated.emit(parsed)

                    # 发射进度信号
                    elif parsed.get('type') == 'train_loss':
                        cur_iter = parsed.get('iter', 0)
                        max_iter = parsed.get('max_iter', 0)
                        if max_iter > 0:
                            self.progress_updated.emit(cur_iter, max_iter)

            # 等待进程结束
            exit_code = process.wait()
            self.training_finished.emit(exit_code)

        except FileNotFoundError as e:
            self.training_error.emit(f"文件未找到: {e}")
            self.training_finished.emit(-1)
        except RuntimeError as e:
            self.training_error.emit(f"运行时错误: {e}")
            self.training_finished.emit(-1)
        except Exception as e:
            self.training_error.emit(f"未知错误: {e}")
            self.training_finished.emit(-1)

    def stop(self):
        """
        请求停止训练。
        
        先设置标志位让日志读取循环退出，
        然后调用 trainer.stop_training() 终止子进程。
        """
        self._should_stop = True
        try:
            self._trainer.stop_training()
        except Exception:
            pass

    @property
    def trainer(self) -> BaseTrainer:
        """获取关联的训练器实例"""
        return self._trainer
