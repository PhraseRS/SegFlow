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
    
    # We want to ignore docstrings. ast.walk doesn't easily distinguish them
    # But usually docstrings are Expr nodes at the start of a module/class/function.
    # To be safe, we'll just extract all string literals and if they have Chinese, add them.
    # We won't translate large multi-line text blocks with docstring format.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            # Check if string contains Chinese characters
            if any('\u4e00' <= c <= '\u9fff' for c in val):
                # ignore if it looks like a docstring (starts and ends with \n or is very long)
                if len(val) > 100 and '\n' in val:
                    # check if it's actually used in UI like setToolTip or QMessageBox
                    # this is hard to do with just ast.walk, but we will print it anyway
                    pass
                chinese_strings.add(val)
                
    return list(chinese_strings)

def main():
    directory = 'd:/WorkSpace/RSegGUI/ui/widgets'
    all_strings = {}
    
    for filename in os.listdir(directory):
        if filename.endswith('.py'):
            file_path = os.path.join(directory, filename)
            strings = extract_chinese_strings(file_path)
            if strings:
                all_strings[filename] = strings
                
    with open('d:/WorkSpace/RSegGUI/scratch/chinese_strings.json', 'w', encoding='utf-8') as f:
        json.dump(all_strings, f, indent=4, ensure_ascii=False)
        
    print(f"Extracted strings saved to scratch/chinese_strings.json")

if __name__ == '__main__':
    main()
