import os
import re
import json

json_path = 'd:/WorkSpace/RSegGUI/i18n/zh_CN.json'
with open(json_path, 'r', encoding='utf-8') as f:
    zh_cn = json.load(f)

directories = ['d:/WorkSpace/RSegGUI/ui']

pattern = re.compile(r'\.(setText|setTitle|setPlaceholderText|setToolTip)\(\s*(["\'])(.*?)(["\'])\s*\)')
msg_pattern = re.compile(r'(QMessageBox\.(?:information|warning|critical|question)\s*\(\s*self\s*,\s*)(["\'])(.*?)(["\'])\s*,\s*(["\'])(.*?)(["\'])\s*\)')

def replacer(match):
    method = match.group(1)
    q1 = match.group(2)
    text = match.group(3)
    q2 = match.group(4)
    if text not in zh_cn: zh_cn[text] = text
    return f'.{method}(self.tr({q1}{text}{q2}))'

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
            
        new_content, num_subs = pattern.subn(replacer, content)
        new_content, msg_subs = msg_pattern.subn(msg_replacer, new_content)
        
        if num_subs > 0 or msg_subs > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Updated {filename}: {num_subs} texts, {msg_subs} msgboxes')

with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(zh_cn, f, ensure_ascii=False, indent=4)
