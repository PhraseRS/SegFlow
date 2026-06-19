import os
import re
import json

# Reverse the replace_phase2.py mapping to get English -> Chinese
from replace_phase2 import replacements as phase2_reps
# Some keys might be duplicated or similar, but this is a good start
eng_to_zh = {v: k for k, v in phase2_reps.items()}

# Also load existing zh_CN.json
json_path = 'd:/WorkSpace/RSegGUI/i18n/zh_CN.json'
with open(json_path, 'r', encoding='utf-8') as f:
    zh_cn = json.load(f)

# Merge known translations
for eng, zh in eng_to_zh.items():
    if eng not in zh_cn:
        zh_cn[eng] = zh

directory = 'd:/WorkSpace/RSegGUI/ui/widgets'

# Regex patterns to find string literals inside specific function calls
# Matches: .setText("some string") or .setTitle('some string')
# Captures: 1: method name, 2: quote char, 3: string content, 4: quote char
pattern = re.compile(r'\.(setText|setTitle|setPlaceholderText|setToolTip)\(\s*(["\'])(.*?)(["\'])\s*\)')

def replacer(match):
    method = match.group(1)
    q1 = match.group(2)
    text = match.group(3)
    q2 = match.group(4)
    
    # Skip if already wrapped (e.g., if it's already self.tr("..."))
    # The regex only matches if the immediate argument is a string literal.
    # So if it was .setText(self.tr("...")), it wouldn't match the pattern.
    
    # Add to dictionary if not present
    if text not in zh_cn:
        zh_cn[text] = text  # default to English if unknown
        
    return f'.{method}(self.tr({q1}{text}{q2}))'

for filename in os.listdir(directory):
    if not filename.endswith('.py'):
        continue
    
    filepath = os.path.join(directory, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    new_content, num_subs = pattern.subn(replacer, content)
    
    # Also handle QMessageBox.information/warning/critical/question
    # This is a bit more complex, let's do a simple one:
    # QMessageBox.xxx(self, "Title", "Text")
    msg_pattern = re.compile(r'(QMessageBox\.(?:information|warning|critical|question)\s*\(\s*self\s*,\s*)(["\'])(.*?)(["\'])\s*,\s*(["\'])(.*?)(["\'])\s*\)')
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
        
    new_content, msg_subs = msg_pattern.subn(msg_replacer, new_content)
    
    if num_subs > 0 or msg_subs > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filename}: {num_subs} texts, {msg_subs} msgboxes")

# Save the updated dictionary
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(zh_cn, f, ensure_ascii=False, indent=4)

print("Translation dictionary updated and strings wrapped.")
