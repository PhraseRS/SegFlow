import json
import os
from PySide6.QtCore import QTranslator

class JsonTranslator(QTranslator):
    """
    基于 JSON 的自定义翻译器。
    从 JSON 文件加载键值对并实现 translate 方法。
    无需依赖 pyside6-lupdate 或 pyside6-lrelease 生成 .qm 文件。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mapping = {}

    def load_json(self, json_path: str) -> bool:
        if not os.path.exists(json_path):
            return False
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.mapping = json.load(f)
            return True
        except Exception as e:
            print(f"[JsonTranslator] Error loading JSON {json_path}: {e}")
            return False

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        """
        重写 QTranslator.translate。
        如果字典中有 sourceText，返回对应的翻译。
        否则回退到原始字符串。
        """
        # 可以支持带上下文的 key: f"{context}::{sourceText}" 
        # 为了简便，这里直接匹配 sourceText
        if sourceText in self.mapping:
            return self.mapping[sourceText]
            
        # 如果有特定前缀或符号，也可以在这里处理
        # A partial JSON catalog must never erase visible UI text. Qt's base
        # translator returns an empty string for a missing key.
        return sourceText
