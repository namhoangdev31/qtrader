import re
import os
from pathlib import Path


def fix_syntax(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for i, line in enumerate(lines):
        new_lines.append(line)
        # Check if this line is a function/class definition ending with :
        if re.search(r"def\s+[\w_]+\(.*\).*:|class\s+[\w_]+.*:", line.strip()):
            # Check if next non-empty line is a def/class or end of file
            is_empty = True
            for next_line in lines[i + 1 :]:
                if next_line.strip():
                    if next_line.startswith(" ") or next_line.startswith("\t"):
                        is_empty = False
                    break

            if is_empty:
                # Add a 'pass' with appropriate indentation
                indent = "    "  # Assume 4 spaces for now
                if line.startswith("    "):
                    indent = "        "
                new_lines.append(f"{indent}pass\n")

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    target_dirs = [Path("/Users/hoangnam/qtrader/qtrader"), Path("/Users/hoangnam/qtrader/tests")]
    for t_dir in target_dirs:
        for root, _, files in os.walk(t_dir):
            for file in files:
                if file.endswith(".py"):
                    fix_syntax(Path(root) / file)


if __name__ == "__main__":
    main()
