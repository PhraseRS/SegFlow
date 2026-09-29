"""异步子进程、日志游标与进程树清理。"""
import asyncio
import json
import os
import signal
import sys
import time

from core.framework_adapters.mmseg_trainer import MMSegTrainer
from mcp_server.session import ROOT, existing_file, session


def interpreter(path=''):
    return existing_file(path or os.environ.get('SEGFLOW_TRAIN_ENV') or sys.executable)


async def terminate(process):
    if process is None or process.returncode is not None:
        return
    try:
        if os.name == 'nt':
            killer = await asyncio.create_subprocess_exec(
                'taskkill', '/PID', str(process.pid), '/T', '/F',
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        await asyncio.wait_for(process.wait(), 5)
    except asyncio.TimeoutError:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        await process.wait()
    except ProcessLookupError:
        pass


async def run(task, command, extra_paths=()):
    parser = MMSegTrainer()
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT), task.work_dir, *extra_paths])
    env['PYTHONIOENCODING'] = 'utf-8'
    try:
        if task.cancel_requested:
            return
        task.process = await asyncio.create_subprocess_exec(
            *command, cwd=task.work_dir, env=env, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, limit=1024 * 1024,
            **({'creationflags': 512} if os.name == 'nt' else {'start_new_session': True}))
        task.status = 'running'
        if task.cancel_requested:
            await terminate(task.process)
        while True:
            raw = await task.process.stdout.readline()
            if not raw:
                break
            line = raw.decode('utf-8', errors='replace').rstrip()
            task.log(line)
            parsed = parser.parse_log_line(line)
            if parsed:
                task.progress.update({k: v for k, v in parsed.items() if k != 'type'})
            if line.startswith('__RS_INFER_PROGRESS__'):
                event = json.loads(line[len('__RS_INFER_PROGRESS__'):])
                task.progress['progress_pct'] = event['value']
            for prefix in ('__MMSEG_TEST_RESULT__', '__SEGFLOW_RESULT__'):
                if line.startswith(prefix):
                    task.result = json.loads(line[len(prefix):])
            if task.events.full():
                task.events.get_nowait()
            task.events.put_nowait(task.snapshot())
        code = await task.process.wait()
        task.status = 'completed' if code == 0 else 'failed'
        if code:
            task.error = f'子进程退出码 {code}; 请读取任务日志'
        elif task.kind in ('evaluation', 'inference', 'config') and not task.result:
            task.status, task.error = 'failed', '子进程未返回结构化结果'
        elif task.kind == 'inference':
            task.progress['progress_pct'] = 100
    except asyncio.CancelledError:
        task.cancel_requested = True
        await terminate(task.process)
        raise
    except Exception as exc:
        task.status, task.error = 'failed', str(exc)
        await terminate(task.process)
    finally:
        if task.cancel_requested:
            task.status = 'cancelled'
        task.ended = time.monotonic()


def launch(kind, work_dir, command, extra_paths=()):
    task = session.add_task(kind, work_dir)
    task.runner = asyncio.create_task(run(task, command, extra_paths))
    return task


async def stop(task):
    if task.status in ('queued', 'running'):
        task.cancel_requested = True
        await terminate(task.process)
        await task.runner
    return task.snapshot()


async def shutdown():
    await asyncio.gather(*(stop(t) for t in list(session.tasks.values())
                           if t.status in ('queued', 'running')), return_exceptions=True)
