"""评估、推理与任务关闭适配测试（不要求 GPU）。"""
import asyncio
import json
import sys

import pytest

from mcp_server.adapters import async_training, requests
from mcp_server.session import session
from mcp_server.tools import evaluation, inference


@pytest.fixture(autouse=True)
def reset():
    session.project = None
    session.tasks.clear()
    yield
    session.tasks.clear()


def test_evaluation_command_and_results(tmp_path, monkeypatch):
    config, checkpoint = tmp_path / 'config.py', tmp_path / 'model.pth'
    config.write_text('')
    checkpoint.write_bytes(b'')
    commands = []
    def fake_launch(kind, directory, command, paths):
        commands.append(command)
        return async_training.launch(kind, directory, [sys.executable, '-u', '-c',
            'print(\'__MMSEG_TEST_RESULT__{"metrics":{"mIoU":82.3,"aAcc":90.1}}\')'])
    monkeypatch.setattr(evaluation, 'launch', fake_launch)
    async def scenario():
        result = await evaluation.evaluate_checkpoint(str(config), str(checkpoint))
        assert result['metrics']['mIoU'] == 82.3
        assert 'core.mmseg_test_runner_entry' in commands[0]
        assert '--custom-module-files-json' in commands[0]
        comparison = await evaluation.compare_checkpoints([str(checkpoint)], str(config))
        assert len(comparison['results']) == 1
    asyncio.run(scenario())


def test_inference_payload(tmp_path, monkeypatch):
    files = [tmp_path / name for name in ('image.tif', 'config.py', 'model.pth')]
    for file in files:
        file.write_bytes(b'')
    original = requests.submit
    def fake_submit(kind, payload, directory, python):
        assert payload['inference_model']['device'] == 'cpu'
        assert payload['block_size'] == 512
        assert payload['overlap'] == .25
        # 保留真实的请求构造及返回状态，替换实际重型子进程。
        from pathlib import Path
        Path(directory).mkdir(parents=True)
        return async_training.launch(kind, directory, [sys.executable, '-u', '-c',
            'print(\'__RS_INFER_PROGRESS__{"value":50}\'); '
            'print(\'__SEGFLOW_RESULT__{"output_mask_path":"test.tif"}\')'])
    monkeypatch.setattr(inference, 'submit', fake_submit)
    async def scenario():
        result = await inference.run_inference(*map(str, files), str(tmp_path),
                                               block_size=512, overlap=.25, device='cpu')
        task = session.task(result['task_id'])
        await task.runner
        status = inference.get_inference_status(task.task_id)
        assert status['progress_pct'] == 100
        assert status['result']['output_mask_path'] == 'test.tif'
        assert (await inference.cancel_inference(task.task_id))['status'] == 'completed'
    asyncio.run(scenario())


def test_shutdown_and_missing_interpreter(tmp_path):
    with pytest.raises(ValueError):
        async_training.interpreter(str(tmp_path / 'missing.exe'))
    async def scenario():
        task = async_training.launch('training', str(tmp_path),
                                     [sys.executable, '-c', 'import time; time.sleep(60)'])
        await async_training.shutdown()
        assert task.status == 'cancelled'
    asyncio.run(scenario())


def test_missing_result_is_failure(tmp_path):
    async def scenario():
        task = async_training.launch('evaluation', str(tmp_path), [sys.executable, '-c', 'pass'])
        await task.runner
        assert task.status == 'failed'
        assert '结构化结果' in task.error
    asyncio.run(scenario())
