import os
import re

def rewrite_file(filepath):
    """
    Finds print(...) and replaces with logger.info(...).
    Also ensures 'from loguru import logger' is present.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        has_print = False
        new_lines = []
        
        for line in lines:
            if 'print(' in line and not line.strip().startswith('#'):
                # Simple replacement for now. 
                # Can be more complex if nested print, but most prints are simple.
                new_line = line.replace('print(', 'logger.info(')
                new_lines.append(new_line)
                has_print = True
            else:
                new_lines.append(line)
        
        if has_print:
            # Check for existing loguru import
            content = "".join(new_lines)
            if 'from loguru import logger' not in content:
                # Add import after __future__ or at top
                insertion_point = 0
                for i, line in enumerate(new_lines):
                    if '__future__' in line:
                        insertion_point = i + 1
                    elif 'import ' in line and insertion_point == 0:
                        insertion_point = i
                
                new_lines.insert(insertion_point, "from loguru import logger\n")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"Rewrote: {filepath}")
            
    except Exception as e:
        print(f"Error rewriting {filepath}: {e}")

for root, dirs, files in os.walk('qtrader'):
    if '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            rewrite_file(os.path.join(root, file))
