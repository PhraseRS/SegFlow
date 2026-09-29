# SegFlow MCP 服务

独立适配层，不修改 `core/`、`ui/`，宿主不导入 Qt 或 PyTorch。  
提供项目、数据集、配置、训练、评估、推理六类工具，以及 `watch_task`（共 **22 个**）。

---

## 一、环境准备

### 1.1 A 层（MCP 宿主环境）

MCP Server 本身只需 Python ≥ 3.10 和少量依赖，**不需要** PyTorch / Qt：

```powershell
# 在 SegFlow 项目根目录执行（建议使用独立虚拟环境）
python -m pip install -r mcp_server/requirements.txt
```

依赖清单（`mcp_server/requirements.txt`）：

| 包 | 说明 |
|---|---|
| `mcp>=1.12,<2` | 官方 MCP Python SDK（含 FastMCP） |
| `numpy>=1.24` | 数据分析辅助 |
| `opencv-python-headless>=4.8` | 图像处理（无 Qt 依赖版本） |

### 1.2 B 层（训练/评估/推理环境）

配置生成需要 `mmengine>=0.10`；训练/评估还需要 PyTorch、MMCV、MMSegmentation；大图推理还需要 GDAL。  
安装方式见仓库根目录 `environment_train.yml`：

```powershell
conda env create -f environment_train.yml
```

---

## 二、启动 MCP Server

> **所有命令均在 SegFlow 项目根目录执行。**

### 2.1 STDIO 模式（推荐，适配所有主流 Agent）

```powershell
# 基本启动（Agent 以子进程方式启动此命令）
python -m mcp_server.server
```

指定 B 层解释器（推荐通过环境变量固定，省去每次传参）：

```powershell
$env:SEGFLOW_TRAIN_ENV = "D:\envs\gui-mmseg\python.exe"
python -m mcp_server.server
```

### 2.2 SSE 模式（可选，适合网页端或远程调用）

```powershell
python -m mcp_server.server --transport sse --port 8765
```

> SSE 模式默认只监听 `127.0.0.1`，**请勿直接对公网开放**。

### 2.3 解释器选择优先级

```
工具参数 python_env_path  →  环境变量 SEGFLOW_TRAIN_ENV  →  当前 Python 解释器
```

显式指定的路径不存在时直接报错，不静默回退。

### 2.4 验证服务器可用

```powershell
# 验证 22 个工具是否正确注册（无需启动完整服务）
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from mcp_server.server import build_server
async def check():
    tools = await build_server().list_tools()
    print(f'OK: {len(tools)} tools registered')
    [print(f'  {t.name}') for t in tools]
asyncio.run(check())
"
```

---

## 三、接入 AI Agent

### 3.1 通用 mcp_config.json（STDIO）

适用于 Claude Desktop、Cursor、Windsurf、Cline、Continue.dev 等支持 `mcp_config.json` 的客户端：

```json
{
  "mcpServers": {
    "segflow": {
      "command": "D:/envs/segflow-mcp/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:/WorkSpace/SegFlow",
      "env": {
        "PYTHONPATH": "D:/WorkSpace/SegFlow",
        "SEGFLOW_TRAIN_ENV": "D:/envs/gui-mmseg/python.exe"
      }
    }
  }
}
```

> 将 `command` 替换为 A 层虚拟环境的 Python 路径，`SEGFLOW_TRAIN_ENV` 指向 B 层（`gui-mmseg`）的解释器。

---

### 3.2 Claude Desktop

配置文件路径：`%APPDATA%\Claude\claude_desktop_config.json`（Windows）

```json
{
  "mcpServers": {
    "segflow": {
      "command": "D:/envs/segflow-mcp/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:/WorkSpace/SegFlow",
      "env": {
        "PYTHONPATH": "D:/WorkSpace/SegFlow",
        "SEGFLOW_TRAIN_ENV": "D:/envs/gui-mmseg/python.exe"
      }
    }
  }
}
```

保存后**重启 Claude Desktop**，在对话框底部「🔌 」图标处可见 `segflow` 已连接，点击查看 22 个工具列表。

---

### 3.3 Cursor

打开 Cursor → Settings → MCP Servers，点击 **Add Server**，填写：

| 字段 | 值 |
|---|---|
| Name | `segflow` |
| Command | `D:\envs\segflow-mcp\Scripts\python.exe -m mcp_server.server` |
| Working Directory | `D:\WorkSpace\SegFlow` |
| Environment | `PYTHONPATH=D:\WorkSpace\SegFlow`，`SEGFLOW_TRAIN_ENV=D:\envs\gui-mmseg\python.exe` |

保存后 Cursor 会自动重启 MCP 进程，Composer 模式下工具列表会出现 `segflow.*`。

---

### 3.4 Antigravity IDE（本工作区）

在 `.agents/` 目录（或全局 `~/.gemini/config/`）创建 `mcp_config.json`：

```json
{
  "mcpServers": {
    "segflow": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:/WorkSpace/SegFlow",
      "env": {
        "PYTHONPATH": "D:/WorkSpace/SegFlow",
        "SEGFLOW_TRAIN_ENV": "D:/envs/gui-mmseg/python.exe"
      }
    }
  }
}
```

> 若 A 层环境即为当前激活环境，`command` 可直接写 `python`。

---

### 3.5 Cline / Continue.dev

在 VSCode 的 `settings.json` 中（或对应插件配置界面）添加：

```json
{
  "cline.mcpServers": {
    "segflow": {
      "command": "D:/envs/segflow-mcp/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:/WorkSpace/SegFlow",
      "env": {
        "PYTHONPATH": "D:/WorkSpace/SegFlow",
        "SEGFLOW_TRAIN_ENV": "D:/envs/gui-mmseg/python.exe"
      }
    }
  }
}
```

---

### 3.6 OpenAI Codex / 自定义 Agent（SSE 模式）

先启动 SSE 服务端：

```powershell
$env:SEGFLOW_TRAIN_ENV = "D:\envs\gui-mmseg\python.exe"
python -m mcp_server.server --transport sse --port 8765
```

Agent 侧使用标准 MCP SSE 客户端连接：

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async with sse_client("http://127.0.0.1:8765/sse") as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print([t.name for t in tools.tools])
```

---

## 四、推荐调用流程

```
1. create_project(project_name, work_dir)       # 或 open_project(project_path)
2. import_dataset(dataset_root)                  # 导入 VOC / images+labels 格式数据集
3. analyze_dataset()                             # 类别分布、健康检查
4. list_available_models()                       # 查看支持的模型/骨干组合
5. get_config_advice()                           # 规则式参数建议
6. generate_config(                              # 生成 MMSeg 配置文件（需 B 层 mmengine）
     model="UperNet",
     backbone="resnet50",
     class_names=["background", "building"],
     epochs=100,
     python_env_path="D:/envs/gui-mmseg/python.exe"
   )
7. start_training(config_path, work_dir,         # 异步启动，立即返回 task_id
                  python_env_path)
8. get_training_status(task_id)                  # 或 stream_training_logs(task_id, cursor=0)
   watch_task(task_id, timeout_seconds=60)       # 接收实时 MCP progress 通知（需客户端提供 progressToken）
9. list_checkpoints(work_dir)                    # 扫描 .pth 文件
10. evaluate_checkpoint(config_path,             # 等待评估，返回 mIoU / aAcc 等真实指标
                        checkpoint_path)
11. run_inference(image_path, config_path,       # 异步大图推理，返回 task_id 和预定输出路径
                  checkpoint_path, output_dir)
12. get_inference_status(task_id)                # 完成后 result.output_mask_path 为有效路径
```

需要中止时：`stop_training(task_id)` / `cancel_inference(task_id)`

---

## 五、重要约定与行为说明

- **数据格式**：支持 VOC（`JPEGImages/SegmentationClass`）和 `images/labels`，同名文件配对。优先读取 `ImageSets/Segmentation` 下的 `train/val/test.txt`；无划分文件时按固定随机种子 42 和默认 8:1:1 划分。不改动源数据，清单保存在项目 `task_config`；小数据集可能出现空划分，需手动提供划分文件。
- **标签缺失**：会在导入摘要中显示，配置生成时拒绝继续。质检复用 `skills.skill_sample_analysis.analyze_sample_fully`，包含其固定类别 ID 规则。
- **配置生成**：实际 API 为 `MMSegTrainer.generate_config`（需 B 层 `mmengine`）。必须显式传入按标签 ID 顺序排列的 `class_names`；`epochs` 自动转换为 `epochs × ceil(train_samples / batch_size)` 次迭代。
- **`get_config_advice`**：`ConfigAdvisor` 是规则引擎，`class_names` 等未在 `analyze_dataset` 输出中的字段会使用空默认值，`hardware_info` 暂不驱动硬件调优。
- **训练**：使用 B 层 `MMEngine Runner`，不创建 `QThread`；日志解析复用 `MMSegTrainer`。
- **评估**：调用 `core.mmseg_test_runner_entry`，返回真实 metrics，不合成缺失的 per-class IoU。`evaluate_checkpoint` / `compare_checkpoints` 同步等待，较长评估需调整客户端超时设置。
- **推理**：在 B 层调用 `InferenceEngine`，拒绝其模拟模式（`use_real_model=False`），验证 Core 的 `success` 标志和输出文件是否存在。取消后目录可能保留部分结果，请勿使用。
- **日志**：每任务保留最近 2000 行，使用 `cursor` 增量轮询。
- **并发限制**：最多 8 个活跃任务、100 条任务记录，同一工作目录不允许并发写入。
- **持久化**：项目状态持久化到 `.rsgproj`，任务进程/状态不支持服务器重启恢复，退出时自动清理活跃子进程。
- **checkpoint 指标**：只关联本次会话中实际评估过的权重，其他为 `null`，绝不按文件名推测指标。

---

## 六、安全边界

这是面向**本地可信用户**的开发工具，不是多租户沙箱：

- Python 配置文件、自定义模块和 checkpoint 均可能执行任意代码，**务必仅使用可信来源的文件**。
- SSE 默认只监听 `127.0.0.1`；不要直接暴露至公网，需要远程部署时另行配置认证和 TLS。
- 多个客户端连接同一进程时共享当前项目和任务状态；需要隔离时为每个客户端启动独立进程。
- STDIO `stdout` 只用于 MCP 协议，Core 层的打印输出发生于子进程，会被捕获为任务日志。

---

## 七、测试

```powershell
# 单元测试（无需 GPU 或 B 层）
python -m pytest tests/test_mcp_server.py tests/test_mcp_protocol.py -q

# 全量测试（含集成测试）
python -m pytest tests -q

# MCP server 内置测试任务
python mcp_server/test_tasks.py
```

测试覆盖：真实 STDIO 握手、工具发现/错误返回、无 Qt/PyTorch 导入、中文路径、数据划分/统计/持久化、`mmengine` 配置生成、真实子进程日志/失败/取消、模拟推理拒绝及部分输出失败识别。  
真实 GPU 训练与 GeoTIFF 推理仍需 B 层环境和真实权重进行端对端验收。
