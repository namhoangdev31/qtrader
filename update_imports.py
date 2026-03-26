import os
import re

replacements = {
    r'\bqtrader\.alpha\b': 'qtrader.feature.alpha',
    r'\bqtrader\.features\b': 'qtrader.feature.features',
    r'\bqtrader\.portfolio\b': 'qtrader.risk.portfolio',
    r'\bqtrader\.feedback\b': 'qtrader.monitoring.feedback',
}

def update_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        new_content = content
        for pattern, replacement in replacements.items():
            new_content = re.sub(pattern, replacement, new_content)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {filepath}")
    except Exception as e:
        print(f"Error updating {filepath}: {e}")

for root, dirs, files in os.walk('qtrader'):
    for file in files:
        if file.endswith('.py'):
            update_file(os.path.join(root, file))
