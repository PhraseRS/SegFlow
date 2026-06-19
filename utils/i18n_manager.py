import os
from PySide6.QtCore import QTranslator, QSettings, QCoreApplication

class I18nManager:
    """
    国际化管理器 (Internationalization Manager)
    负责读取用户配置的语言，并加载相应的 QTranslator
    """
    SETTINGS_ORG = "RSegGUI"
    SETTINGS_APP = "RSegGUI"
    
    # 默认语言
    DEFAULT_LANG = "en"
    
    @classmethod
    def get_current_language(cls) -> str:
        """获取当前配置的语言"""
        settings = QSettings(cls.SETTINGS_ORG, cls.SETTINGS_APP)
        return settings.value("language", cls.DEFAULT_LANG)

    @classmethod
    def set_language(cls, lang_code: str):
        """设置用户偏好语言"""
        settings = QSettings(cls.SETTINGS_ORG, cls.SETTINGS_APP)
        settings.setValue("language", lang_code)

    @classmethod
    def setup_translator(cls, app: QCoreApplication):
        """
        初始化并加载翻译器。
        必须在主窗口初始化之前调用！
        """
        lang = cls.get_current_language()
        
        # 因为代码的源语言是英文，所以当选择 'en' 时，不需要加载翻译包
        if lang == "en":
            return
            
        # 当选择了其他语言 (如 'zh_CN')
        translator = QTranslator()
        
        # 查找 i18n 目录下的语言包
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        json_path = os.path.join(base_dir, "i18n", f"{lang}.json")
        
        from utils.json_translator import JsonTranslator
        translator = JsonTranslator(app)
        
        if translator.load_json(json_path):
            app.installTranslator(translator)
        else:
            print(f"[I18nManager] Cannot load translation file: {json_path}")

