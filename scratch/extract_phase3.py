import os
import ast
import json

def extract_chinese_strings(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return []

    chinese_strings = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if any('\u4e00' <= c <= '\u9fff' for c in val):
                if len(val) > 100 and '\n' in val:
                    pass
                chinese_strings.add(val)
                
    return list(chinese_strings)

def main():
    directory = 'd:/WorkSpace/RSegGUI/ui'
    files_to_check = ['analysis_panel.py', 'inference_panel.py']
    all_strings = {}
    
    for filename in files_to_check:
        file_path = os.path.join(directory, filename)
        strings = extract_chinese_strings(file_path)
        if strings:
            all_strings[filename] = strings
                
    with open('d:/WorkSpace/RSegGUI/scratch/chinese_strings_phase3.json', 'w', encoding='utf-8') as f:
        json.dump(all_strings, f, indent=4, ensure_ascii=False)
        
    print(f"Extracted strings saved to scratch/chinese_strings_phase3.json")

if __name__ == '__main__':
    main()
