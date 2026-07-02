from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, Signal, Slot

from core.toolbox_registry import Toolbox, ToolboxTool


class ToolRunner(QObject):
    started = Signal(str)
    outputLine = Signal(str)
    eventReceived = Signal(dict)
    finished = Signal(int)
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._process: QProcess | None = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    def start(self, toolbox: Toolbox, tool: ToolboxTool, values: dict[str, object]) -> None:
        if self.is_running():
            raise RuntimeError("A toolbox task is already running")
        if not tool.runnable:
            raise RuntimeError(f"{tool.name} is installed but not parameterized for GUI execution yet")

        args = ["-m", toolbox.entrypoint, *tool.command]
        resolved_values = {param.name: values.get(param.name, param.default) for param in tool.parameters}
        for param in tool.parameters:
            if not self._parameter_is_active(param, resolved_values):
                continue
            value = resolved_values.get(param.name)
            if param.type == "boolean":
                if bool(value) and param.flag:
                    args.append(param.flag)
                continue
            if value is None or str(value).strip() == "":
                if param.required:
                    raise ValueError(f"Missing required parameter: {param.label}")
                continue
            if param.type == "string_list":
                parts = [part for part in str(value).replace(",", " ").split() if part]
                if not parts:
                    if param.required:
                        raise ValueError(f"Missing required parameter: {param.label}")
                    continue
                if param.flag:
                    args.append(param.flag)
                args.extend(parts)
                continue
            if param.flag:
                args.extend([param.flag, str(value)])
            else:
                args.append(str(value))

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(args)
        process.setWorkingDirectory(str(toolbox.root))

        env = process.processEnvironment()
        existing_pythonpath = env.value("PYTHONPATH", "")
        pythonpath = str(toolbox.root)
        if existing_pythonpath:
            pythonpath = pythonpath + os.pathsep + existing_pythonpath
        env.insert("PYTHONPATH", pythonpath)
        process.setProcessEnvironment(env)

        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_finished)

        self._process = process
        self.started.emit(tool.id)
        process.start()

    def _parameter_is_active(self, param, values: dict[str, object]) -> bool:
        for name, expected in param.visible_when.items():
            actual = values.get(name)
            if isinstance(expected, (list, tuple, set)):
                if str(actual) not in {str(item) for item in expected}:
                    return False
                continue
            if str(actual) != str(expected):
                return False
        return True

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()

    @Slot()
    def _read_stdout(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._handle_output(text)

    @Slot()
    def _read_stderr(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._handle_output(text)

    def _handle_output(self, text: str) -> None:
        for line in text.splitlines():
            if not line:
                continue
            self.outputLine.emit(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self.eventReceived.emit(event)

    @Slot(QProcess.ProcessError)
    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        self.errorOccurred.emit(str(error))

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.finished.emit(exit_code)
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
