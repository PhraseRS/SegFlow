"""B 层大图推理，不在 MCP 宿主加载 torch。"""
import uuid
from pathlib import Path

from mcp_server.adapters.async_training import stop
from mcp_server.adapters.requests import custom_modules, submit
from mcp_server.session import existing_file, session


async def run_inference(image_path: str, config_path: str, checkpoint_path: str,
                        output_dir: str, block_size: int = 1024, overlap: float = 0.2,
                        python_env_path: str = '', device: str = 'cuda:0',
                        enable_tta: bool = False) -> dict:
    """立即返回异步任务 ID 和预定输出路径；仅 completed 后输出才有效。"""
    if block_size < 32 or not 0 <= overlap < 1 or int(block_size * (1 - overlap)) < 1:
        raise ValueError('block_size >= 32，overlap 必须在 [0,1)，且步长至少 1')
    image, config, checkpoint = map(existing_file, (image_path, config_path, checkpoint_path))
    directory = Path(output_dir).expanduser().resolve() / ('inference-' + uuid.uuid4().hex)
    output = str(directory / (Path(image).stem + '_mask.tif'))
    modules = custom_modules(config)
    payload = dict(image_path=image, output_path=output, block_size=block_size,
                   overlap=overlap, enable_tta=enable_tta, custom_module_files=modules,
                   inference_model=dict(config=config, checkpoint=checkpoint, device=device,
                                        custom_module_files=modules))
    task = submit('inference', payload, str(directory), python_env_path)
    return {**task.snapshot(), 'output_mask_path': output}


def get_inference_status(task_id: str) -> dict:
    """返回进度、耗时与完成后的输出路径。"""
    return session.task(task_id, 'inference').snapshot()


async def cancel_inference(task_id: str) -> dict:
    """终止推理进程树；取消后目录可能包含不完整产物，不应使用。"""
    return await stop(session.task(task_id, 'inference'))
