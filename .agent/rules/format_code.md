# Code Formatting Rule

## Context
Consistent code style is essential for maintainability. This project uses `black` for Python code formatting.

## Rule
- **Format Required**: AFTER modifying or creating any Python file (`.py`), you MUST run `black` on that file.
- **Command**: `poetry run black <filename>`
- **Scope**: Apply this to any file you touch.
