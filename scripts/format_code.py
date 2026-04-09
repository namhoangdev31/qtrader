import os
import subprocess
import sys
from pathlib import Path


def find_ruff():
    """Finds the ruff executable."""
    common_paths = [
        "/opt/homebrew/bin/ruff",
        "/usr/local/bin/ruff",
        "ruff",  # fall back to PATH
    ]
    for path in common_paths:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None


def run_formatter():
    """Runs ruff format on qtrader/ and tests/."""
    ruff_path = find_ruff()
    if not ruff_path:
        print("Error: 'ruff' command not found in common paths or PATH.")
        sys.exit(1)

    root_dir = Path("/Users/hoangnam/qtrader")
    target_dirs = ["qtrader", "tests"]

    cmd = [ruff_path, "format"] + target_dirs
    print(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            print("Formatting successful!")
            print(result.stdout)
        else:
            print("Formatting failed or found issues.")
            print(result.stderr)
            sys.exit(result.returncode)

    except FileNotFoundError:
        print("Error: 'ruff' command not found. Please ensure it is installed.")
        sys.exit(1)


if __name__ == "__main__":
    run_formatter()
    # also run ruff check --fix to cleanup unused imports if any (though strip_docs didn't touch imports)
    # subprocess.run(["ruff", "check", "--fix", "qtrader", "tests"], cwd="/Users/hoangnam/qtrader")
