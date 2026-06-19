import os
import re
import json

json_path = 'd:/WorkSpace/RSegGUI/i18n/zh_CN.json'
with open(json_path, 'r', encoding='utf-8') as f:
    zh_cn = json.load(f)

directories = ['d:/WorkSpace/RSegGUI/ui/widgets', 'd:/WorkSpace/RSegGUI/ui']

pattern1 = re.compile(r'\.(setText|setTitle|setPlaceholderText|setToolTip)\(\s*(["\'])(.*?)(["\'])\s*\)')
pattern2 = re.compile(r'(QLabel|QPushButton|QCheckBox|QRadioButton|QGroupBox|QAction|QMenu)\(\s*(["\'])(.*?)(["\'])\s*([,)])')
msg_pattern = re.compile(r'(QMessageBox\.(?:information|warning|critical|question)\s*\(\s*self\s*,\s*)(["\'])(.*?)(["\'])\s*,\s*(["\'])(.*?)(["\'])\s*\)')

def replacer1(match):
    method = match.group(1)
    q1 = match.group(2)
    text = match.group(3)
    q2 = match.group(4)
    if text not in zh_cn: zh_cn[text] = text
    return f'.{method}(self.tr({q1}{text}{q2}))'

def replacer2(match):
    cls = match.group(1)
    q1 = match.group(2)
    text = match.group(3)
    q2 = match.group(4)
    suffix = match.group(5)
    if text not in zh_cn: zh_cn[text] = text
    return f'{cls}(self.tr({q1}{text}{q2}){suffix}'

def msg_replacer(match):
    prefix = match.group(1)
    q1 = match.group(2)
    title = match.group(3)
    q2 = match.group(4)
    q3 = match.group(5)
    text = match.group(6)
    q4 = match.group(7)
    if title not in zh_cn: zh_cn[title] = title
    if text not in zh_cn: zh_cn[text] = text
    return f'{prefix}self.tr({q1}{title}{q2}), self.tr({q3}{text}{q4})'

for directory in directories:
    for filename in os.listdir(directory):
        if not filename.endswith('.py') or filename.endswith('_ui.py'):
            continue
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        new_content, n1 = pattern1.subn(replacer1, content)
        new_content, n2 = pattern2.subn(replacer2, new_content)
        new_content, msg_subs = msg_pattern.subn(msg_replacer, new_content)
        
        if n1 > 0 or n2 > 0 or msg_subs > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Updated {filename}: {n1} texts, {n2} instantiations, {msg_subs} msgboxes')

with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(zh_cn, f, ensure_ascii=False, indent=4)
