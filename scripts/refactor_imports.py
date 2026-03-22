import os
import re

MAPPINGS = [
    (r"qtrader\.input\.alpha", r"qtrader.alpha"),
    (r"qtrader\.input\.data", r"qtrader.data"),
    (r"qtrader\.input\.features", r"qtrader.features"),
    (r"qtrader\.input\.api", r"qtrader.api"),
    (r"qtrader\.output\.analyst", r"qtrader.research"),
    (r"qtrader\.output\.analytics", r"qtrader.analytics"),
    (r"qtrader\.output\.bot", r"bot"),
    (r"qtrader\.output\.execution", r"qtrader.execution"),
    (r"qtrader\.output\.portfolio", r"qtrader.portfolio"),
    (r"qtrader\.output\.risk", r"qtrader.risk"),
    (r"\bfrom\s+backtest\b", r"from qtrader.backtest"),
    (r"\bimport\s+backtest\b", r"import qtrader.backtest"),
    (r"\bfrom\s+portfolio\b", r"from qtrader.portfolio"),
    (r"\bimport\s+portfolio\b", r"import qtrader.portfolio"),
    (r"\bfrom\s+risk\b", r"from qtrader.risk"),
    (r"\bimport\s+risk\b", r"import qtrader.risk"),
    (r"\bfrom\s+execution\b", r"from qtrader.execution"),
    (r"\bimport\s+execution\b", r"import qtrader.execution"),
]

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for pattern, repl in MAPPINGS:
        new_content = re.sub(pattern, repl, new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

def main():
    root_dir = "/Users/hoangnam/qtrader"
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if ".venv" in dirpath or ".git" in dirpath or ".kilo" in dirpath or "rust_core" in dirpath or "node_modules" in dirpath:
            continue
        for filename in filenames:
            if filename.endswith(".py") or filename.endswith(".ipynb"):
                process_file(os.path.join(dirpath, filename))

if __name__ == "__main__":
    main()
