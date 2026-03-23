---
description: Create a new trading module and its corresponding unit test file
---

This workflow enforces Test-Driven Development (TDD) and strict architectural boundaries when adding new components to the system.

1. **Verify Target Directory**: Ensure the new module belongs in an existing core directory like `qtrader/features/`, `qtrader/alpha/`, or `qtrader/risk/`. Do NOT create a new top-level directory.
2. **Create Test Scaffold First**: Identify the target path `qtrader/<module>/<file>.py` and IMMEDATEILY create `tests/unit/<module>/test_<file>.py`.
3. **Write Unit Tests First**: Write the unit tests covering edge cases (empty dataframes, NaNs, missing columns) BEFORE writing the implementation.
4. **Implement Logic**: Write the code in `qtrader/<module>/<file>.py` utilizing Polars for data manipulation and ensuring strict type hints.
5. **Iterate Verification**: Run the tests repeatedly until they pass.
// turbo
6. Run the new tests: `pytest tests/unit/<MODULE_NAME>/test_<FILE_NAME>.py -v`
// turbo
7. Verify type hints for the new file: `mypy qtrader/<MODULE_NAME>/<FILE_NAME>.py --strict`
