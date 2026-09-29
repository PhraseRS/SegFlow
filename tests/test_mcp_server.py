"""MCP 无 GPU 回归测试：真实文件/真实子进程/真实配置生成。"""
import asyncio
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from mcp_server.session import session
from mcp_server.tools import config, dataset, project, training
from mcp_server.adapters.async_training import launch, stop


@pytest.fixture(autouse=True)
def clean_session():
    session.project = None
    session.tasks.clear()
    yield
    session.project = None
    session.tasks.clear()


@pytest.fixture
def imported(tmp_path):
    import cv2
    root = tmp_path / '数据'
    (root / 'images').mkdir(parents=True)
    (root / 'labels').mkdir()
    for i in range(10):
        cv2.imencode('.png', np.ones((32, 32, 3), dtype=np.uint8))[1].tofile(str(root / 'images' / f'{i}.png'))
        cv2.imencode('.png', np.ones((32, 32), dtype=np.uint8))[1].tofile(str(root / 'labels' / f'{i}.png'))
    project.create_project('测试', str(tmp_path / 'work'))
    return dataset.import_dataset(str(root))


def test_project_dataset_roundtrip(imported):
    assert imported['splits'] == {'train': 8, 'val': 1, 'test': 1}
    assert dataset.list_samples('train', 2, 1)['total'] == 8
    stats = dataset.analyze_dataset()
    assert stats['pixel_distribution'] == {'1': 10240}
    assert stats['pixel_ratios'] == {'1': 1.0}
    path = session.project.project_path
    project.open_project(path)
    assert dataset.list_samples()['total'] == 10
    assert config.get_config_advice()['loss_config']
    with pytest.raises(ValueError):
        project.create_project('测试', str(Path(path).parent))
    with pytest.raises(ValueError):
        dataset.list_samples(limit=0)


def test_bad_input(imported):
    root = session.project.inputs.dataset_root
    with pytest.raises(ValueError):
        dataset.import_dataset(root, [1, 1, 1])
    (Path(root) / 'train.txt').write_text('0\n0\n')
    with pytest.raises(ValueError, match='重复'):
        dataset.import_dataset(root)
    with pytest.raises(ValueError):
        training.get_training_status('unknown')


def test_process_logs_failure_cancel(tmp_path):
    async def scenario():
        task = launch('training', str(tmp_path), [sys.executable, '-u', '-c',
                      "print('Iter(train) [10/100] lr: 1.0e-3 loss: 0.25 eta: 1:00:00')"])
        await task.runner
        assert task.status == 'completed'
        assert task.progress['iter'] == 10
        assert task.progress['loss'] == .25
        logs = training.stream_training_logs(task.task_id)
        assert len(logs['lines']) == 1
        assert not training.stream_training_logs(task.task_id, logs['next_cursor'])['lines']
        failed = launch('training', str(tmp_path), [sys.executable, '-c', 'raise RuntimeError("bad")'])
        await failed.runner
        assert failed.status == 'failed'
        sleeper = launch('training', str(tmp_path), [sys.executable, '-c', 'import time; time.sleep(60)'])
        await stop(sleeper)
        assert sleeper.status == 'cancelled'
        sleeper = launch('training', str(tmp_path), [sys.executable, '-c', 'import time; time.sleep(60)'])
        while sleeper.status == 'queued':
            await asyncio.sleep(.01)
        await stop(sleeper)
        assert sleeper.process.returncode is not None
        assert sleeper.status == 'cancelled'
    asyncio.run(scenario())


def test_real_config_generation(imported, tmp_path):
    pytest.importorskip('mmengine')
    base = tmp_path / 'base.py'
    base.write_text("""model = dict(type='EncoderDecoder', backbone=dict(type='ResNet', depth=50),
    decode_head=dict(type='FCNHead', num_classes=2))
train_cfg = dict(type='IterBasedTrainLoop', max_iters=100, val_interval=10)
optim_wrapper = dict(optimizer=dict(type='SGD', lr=0.01))
param_scheduler = []
default_hooks = dict(checkpoint=dict(type='CheckpointHook', interval=10))
train_dataloader = dict(batch_size=2, num_workers=0, dataset=dict(type='BaseSegDataset',
    data_root='', data_prefix=dict(img_path='x', seg_map_path='y'), ann_file='old_train.txt'))
val_dataloader = dict(batch_size=1, num_workers=0, dataset=dict(type='BaseSegDataset',
    data_root='', data_prefix=dict(img_path='x', seg_map_path='y'), ann_file='old_val.txt'))
test_dataloader = dict(batch_size=1, num_workers=0, dataset=dict(type='BaseSegDataset',
    data_root='', data_prefix=dict(img_path='x', seg_map_path='y'), ann_file='old_test.txt'))
""", encoding='utf-8')
    result = asyncio.run(config.generate_config('upernet', 'r50', epochs=3,
                         base_config=str(base), class_names=['background', 'building']))
    assert result['max_iters'] == 12
    text = config.preview_config(result['config_path'])['content']
    assert 'old_train.txt' not in text
    assert 'images' in text
    assert Path(result['config_path']).with_name('custom_rs_dataset.py').is_file()
    assert session.project.model.config == result['config_path']


def test_bounded_logs_and_registry(tmp_path):
    task = session.add_task('training', str(tmp_path))
    for i in range(3000):
        task.log(str(i))
    assert len(task.logs) == 2000
    assert training.stream_training_logs(task.task_id)['truncated']
    with pytest.raises(ValueError, match='已有'):
        session.add_task('training', str(tmp_path))
