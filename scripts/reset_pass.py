import os
from pathlib import Path

def reset_pass(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip() == "pass":
            continue
        new_lines.append(line)

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def main():
    target_dirs = [
        Path("/Users/hoangnam/qtrader/qtrader"),
        Path("/Users/hoangnam/qtrader/tests")
    ]
    for t_dir in target_dirs:
        for root, _, files in os.walk(t_dir):
            for file in files:
                if file.endswith(".py"):
                    reset_pass(Path(root) / file)

if __name__ == "__main__":
    main()
