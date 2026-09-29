"""真实 STDIO 协议握手及 worker 边界测试。"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_server.session import ROOT


def test_stdio_protocol(tmp_path):
    pytest.importorskip('mcp')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(command=sys.executable,
                                       args=['-m', 'mcp_server.server'], cwd=str(ROOT))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert len(tools.tools) == 22
                result = await client.call_tool('create_project',
                                               {'project_name': 'protocol', 'work_dir': str(tmp_path)})
                assert not result.isError
                result = await client.call_tool('get_project_status', {})
                assert not result.isError
                result = await client.call_tool('get_training_status', {'task_id': 'missing'})
                assert result.isError
                result = await client.call_tool('list_available_models', {})
                assert not result.isError
    asyncio.run(scenario())


def test_headless_import():
    import subprocess
    code = "from mcp_server.server import build_server; import sys; build_server(); assert 'PySide6' not in sys.modules; assert 'torch' not in sys.modules"
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_inference_rejects_mock(monkeypatch, tmp_path):
    from mcp_server.adapters.worker import infer
    closed = []
    class FakeEngine:
        use_real_model = False
        def __init__(self, info):
            pass
        def close(self):
            closed.append(True)
    monkeypatch.setitem(sys.modules, 'core.inference_engine', SimpleNamespace(InferenceEngine=FakeEngine))
    with pytest.raises(RuntimeError, match='模拟'):
        infer({'inference_model': {}})
    assert closed


def test_inference_rejects_partial_output(monkeypatch, tmp_path):
    from mcp_server.adapters.worker import infer
    output = tmp_path / 'mask.tif'
    class FakeEngine:
        use_real_model = True
        def __init__(self, info):
            pass
        def close(self):
            pass
        def set_progress_callback(self, callback):
            pass
        def large_image_block_inference(self, *args, **kwargs):
            output.write_bytes(b'partial')
            return {'success': False, 'error': 'out of memory'}
    monkeypatch.setitem(sys.modules, 'core.inference_engine', SimpleNamespace(InferenceEngine=FakeEngine))
    with pytest.raises(RuntimeError, match='out of memory'):
        infer(dict(inference_model={}, image_path='image.tif', output_path=str(output),
                   block_size=512, overlap=.2, enable_tta=False))
