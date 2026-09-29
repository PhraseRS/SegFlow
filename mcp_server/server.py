"""启动：python -m mcp_server.server [--transport sse --port 8765]。"""
import argparse
import asyncio
import functools
import inspect
from contextlib import asynccontextmanager

from mcp.server.fastmcp import Context, FastMCP
from mcp_server.adapters.async_training import shutdown
from mcp_server.session import session
from mcp_server.tools import config, dataset, evaluation, inference, project, training


@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await shutdown()


def build_server(port=8765):
    server = FastMCP('SegFlow', host='127.0.0.1', port=port, lifespan=lifespan,
                     instructions='本地可信工作区工具。Python 配置会执行代码；仅使用可信文件。长任务请轮询。')
    mutating = {'create_project', 'open_project', 'import_dataset', 'analyze_dataset',
                'generate_config', 'set_pretrain_weights'}

    def register(function):
        @functools.wraps(function)
        async def wrapped(*args, **kwargs):
            async def invoke():
                if inspect.iscoroutinefunction(function):
                    return await function(*args, **kwargs)
                return await asyncio.to_thread(function, *args, **kwargs)
            if function.__name__ in mutating:
                async with session.lock:
                    return await invoke()
            return await invoke()
        server.tool()(wrapped)

    for module in (project, dataset, config, training, evaluation, inference):
        for name, function in vars(module).items():
            if not name.startswith('_') and inspect.isfunction(function) and function.__module__ == module.__name__:
                register(function)

    @server.tool()
    async def watch_task(task_id: str, ctx: Context, timeout_seconds: float = 30) -> dict:
        """等待最多 120 秒，并在本次请求期间发送 MCP progress 通知。

        客户端需提供 progressToken；任务启动请求结束后请用轮询或本工具跟踪。
        """
        if not 0 < timeout_seconds <= 120:
            raise ValueError('timeout_seconds 必须在 (0,120]')
        task = session.task(task_id)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while task.status in ('queued', 'running') and asyncio.get_running_loop().time() < deadline:
            progress = task.progress
            await ctx.report_progress(progress=progress.get('progress_pct', progress.get('iter', 0)),
                                      total=100 if task.kind == 'inference' else progress.get('max_iter'),
                                      message=task.status)
            await asyncio.sleep(0.5)
        await ctx.report_progress(progress=task.progress.get('progress_pct', task.progress.get('iter', 0)),
                                  message=task.status)
        return task.snapshot()

    return server


def main():
    parser = argparse.ArgumentParser(description='SegFlow 本地 MCP 服务')
    parser.add_argument('--transport', choices=['stdio', 'sse'], default='stdio')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port 必须在 1–65535')
    build_server(args.port).run(transport=args.transport)


if __name__ == '__main__':
    main()
