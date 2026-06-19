import os

directories = ['d:/WorkSpace/RSegGUI/ui/widgets', 'd:/WorkSpace/RSegGUI/ui']

count = 0
for d in directories:
    for f in os.listdir(d):
        if not f.endswith('.py'): continue
        filepath = os.path.join(d, f)
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        lines = content.split('\n')
        changed = False
        for i, line in enumerate(lines):
            if 'QMessageBox.' in line and 'self.tr' in line:
                opens = line.count('(')
                closes = line.count(')')
                if opens > closes:
                    lines[i] = line + ')' * (opens - closes)
                    changed = True
                    count += 1
        
        if changed:
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write('\n'.join(lines))
            print(f'Fixed {f}')

print(f'Fixed {count} broken QMessageBox lines')
