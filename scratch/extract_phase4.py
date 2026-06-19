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
    directories = ['d:/WorkSpace/RSegGUI/core', 'd:/WorkSpace/RSegGUI/utils']
    all_strings = {}
    
    for directory in directories:
        if not os.path.exists(directory):
            continue
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.endswith('.py'):
                    file_path = os.path.join(root, filename)
                    strings = extract_chinese_strings(file_path)
                    if strings:
                        # Use relative path as key
                        rel_path = os.path.relpath(file_path, 'd:/WorkSpace/RSegGUI')
                        all_strings[rel_path] = strings
                
    with open('d:/WorkSpace/RSegGUI/scratch/chinese_strings_phase4.json', 'w', encoding='utf-8') as f:
        json.dump(all_strings, f, indent=4, ensure_ascii=False)
        
    print(f"Extracted strings saved to scratch/chinese_strings_phase4.json")

if __name__ == '__main__':
    main()
