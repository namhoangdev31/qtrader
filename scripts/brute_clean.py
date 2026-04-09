import os
import re
from pathlib import Path


def get_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def brute_fix(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    processed_lines = []
    for i, line in enumerate(lines):
        # Remove trailing whitespace but keep newline
        clean_line = line.rstrip() + "\n"
        processed_lines.append(clean_line)

        # Only if line ends in : and starts with a block keyword
        stripped = clean_line.strip()
        is_block_start = False
        block_keywords = [
            "def ",
            "class ",
            "if ",
            "elif ",
            "else:",
            "for ",
            "while ",
            "try:",
            "except",
            "finally:",
            "with ",
            "async ",
        ]

        if stripped.endswith(":"):
            for kw in block_keywords:
                if stripped.startswith(kw):
                    is_block_start = True
                    break

        if is_block_start:
            # Check indentation of the line itself
            current_indent = get_indent(clean_line)

            # Find next non-empty line
            next_line = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    next_line = lines[j]
                    break

            if not next_line:
                # End of file after colon
                processed_lines.append(" " * (current_indent + 4) + "pass\n")
            else:
                next_indent = get_indent(next_line)
                if next_indent <= current_indent:
                    # Next line is not indented enough -> empty block
                    processed_lines.append(" " * (current_indent + 4) + "pass\n")

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(processed_lines)


def main():
    target_dirs = [Path("/Users/hoangnam/qtrader/qtrader"), Path("/Users/hoangnam/qtrader/tests")]
    for t_dir in target_dirs:
        for root, _, files in os.walk(t_dir):
            for file in files:
                if file.endswith(".py"):
                    brute_fix(Path(root) / file)


if __name__ == "__main__":
    main()
