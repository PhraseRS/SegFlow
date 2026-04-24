import json
import os
import subprocess
from typing import Dict, List, Optional


class MMSegEnvManager:
    def __init__(self):
        self.conda_bin = self._get_conda_path()

    def _get_conda_path(self) -> Optional[str]:
        """Try common conda entrypoints without assuming PATH is configured."""
        candidates = []

        conda_exe = os.environ.get("CONDA_EXE")
        if conda_exe:
            candidates.append(conda_exe)

        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            if os.name == "nt":
                candidates.append(os.path.join(conda_prefix, "Scripts", "conda.exe"))
                candidates.append(os.path.join(conda_prefix, "condabin", "conda.bat"))
            else:
                candidates.append(os.path.join(conda_prefix, "bin", "conda"))

        if os.name == "nt":
            candidates.extend(
                [
                    "conda.exe",
                    "conda",
                    os.path.expandvars(r"%USERPROFILE%\miniconda3\Scripts\conda.exe"),
                    os.path.expandvars(r"%USERPROFILE%\anaconda3\Scripts\conda.exe"),
                    r"D:\miniconda\Scripts\conda.exe",
                    r"D:\anaconda3\Scripts\conda.exe",
                ]
            )
        else:
            candidates.extend(
                [
                    "conda",
                    os.path.expanduser("~/miniconda3/bin/conda"),
                    os.path.expanduser("~/anaconda3/bin/conda"),
                ]
            )

        for candidate in candidates:
            if not candidate:
                continue
            try:
                subprocess.check_output(
                    [candidate, "--version"],
                    stderr=subprocess.STDOUT,
                    timeout=5,
                    env=self._conda_env_vars(),
                )
                return candidate
            except Exception:
                continue
        return None

    def _conda_env_vars(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.setdefault("CONDA_NO_PLUGINS", "true")
        return env

    def list_all_envs(self) -> List[Dict[str, str]]:
        """Return detected conda envs and their python executables."""
        if not self.conda_bin:
            return []

        try:
            raw_out = subprocess.check_output(
                [self.conda_bin, "env", "list", "--json"],
                text=True,
                timeout=8,
                env=self._conda_env_vars(),
            )
            env_paths = json.loads(raw_out).get("envs", [])
        except Exception:
            return []

        result = []
        for env_path in env_paths:
            if os.name == "nt":
                python_exe = os.path.join(env_path, "python.exe")
            else:
                python_exe = os.path.join(env_path, "bin", "python")

            if not os.path.exists(python_exe):
                continue

            name = os.path.basename(env_path.rstrip("\\/")) or env_path
            result.append(
                {
                    "name": name,
                    "path": python_exe,
                    "display_name": f"{name} - {python_exe}",
                }
            )
        return result

    def check_env_health(self, python_path: str) -> Dict[str, object]:
        """
        Probe a Python interpreter for torch/MMCV/MMSeg availability and CUDA state.
        """
        if not python_path or not os.path.exists(python_path):
            return {"status": "error", "msg": f"Python path does not exist: {python_path}"}

        probe_code = "\n".join(
            [
                "import json",
                "import sys",
                "res = {'status': 'ready', 'details': {'python': sys.version.split()[0]}}",
                "try:",
                "    import torch",
                "    res['details']['torch'] = torch.__version__",
                "    res['details']['cuda'] = torch.cuda.is_available()",
                "    try:",
                "        import mmcv",
                "        res['details']['mmcv'] = mmcv.__version__",
                "    except Exception as exc:",
                "        res['status'] = 'incomplete'",
                "        res['msg'] = f'mmcv import failed: {exc}'",
                "    try:",
                "        import mmseg",
                "        res['details']['mmseg'] = mmseg.__version__",
                "    except Exception as exc:",
                "        res['status'] = 'incomplete'",
                "        if 'msg' in res:",
                "            res['msg'] += f'; mmseg import failed: {exc}'",
                "        else:",
                "            res['msg'] = f'mmseg import failed: {exc}'",
                "except Exception as exc:",
                "    res['status'] = 'error'",
                "    res['msg'] = str(exc)",
                "print(json.dumps(res, ensure_ascii=False))",
            ]
        )

        try:
            output = subprocess.check_output(
                [python_path, "-c", probe_code],
                text=True,
                timeout=10,
            )
            return json.loads(output.strip())
        except Exception as exc:
            return {"status": "error", "msg": f"Interpreter probe failed: {exc}"}

    def validate_environment(self, python_path: str):
        """Validate the selected Python environment."""
        result = self.check_env_health(python_path)
        details = result.get("details", {})

        if result.get("status") == "ready":
            return (
                True,
                "Ready: "
                f"Python {details.get('python', '?')} | "
                f"Torch {details.get('torch', '?')} | "
                f"MMCV {details.get('mmcv', '?')} | "
                f"MMSeg {details.get('mmseg', '?')} | "
                f"CUDA {'Available' if details.get('cuda') else 'Not Available'}",
            )

        if result.get("status") == "incomplete":
            return (
                False,
                "Incomplete environment: "
                f"Python {details.get('python', '?')} | "
                f"Torch {details.get('torch', '?')} | "
                f"{result.get('msg', 'Missing MMCV/MMSeg components')}",
            )

        return False, f"Validation failed: {result.get('msg', 'Unknown error')}"
