import os
import re

def clean_file(filepath):
    """
    Removes TODO comments and dead code hints.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            # Remove TODO comments
            # Matches: # TODO: ... or #TODO ... 
            # We keep the code before the comment if it exists.
            if 'TODO' in line:
                # Use regex to replace only the TODO part if it's a comment
                line = re.sub(r'#.*TODO.*$', '', line).rstrip()
                if line: # If line still has content, keep it
                    new_lines.append(line + '\n')
            else:
                new_lines.append(line)
        
        # Only write if modified
        if new_lines != lines:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"Cleaned TODOs: {filepath}")
            
    except Exception as e:
        print(f"Error cleaning {filepath}: {e}")

for root, dirs, files in os.walk('qtrader'):
    if '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            clean_file(os.path.join(root, file))
