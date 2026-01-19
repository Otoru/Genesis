---
description: Run tests and validate code before pushing, ensuring dependencies are installed.
---

# Test and Validate Workflow

This workflow ensures that all tests pass and dependencies are installed before any code is pushed or PR is created.

1. **Check for Poetry**
   Ensure `poetry` is available.
   ```bash
   poetry --version
   ```

2. **Install Dependencies**
   // turbo
   Ensure all dependencies are installed.
   ```bash
   poetry install
   ```

3. **Run Linter (Black)**
   // turbo
   Ensure code formatting compliance.
   ```bash
   poetry run black . --check
   ```
   *If this fails, run `poetry run black .` to automatically fix formatting.*

4. **Run Type Checker (Mypy)**
   // turbo
   Ensure type safety.
   ```bash
   poetry run mypy
   ```

5. **Run Tests**
   // turbo
   Run the test suite.
   ```bash
   poetry run py.test
   ```

6. **Verify No Warnings**
   // turbo
   Ensure tests run without warnings.
   ```bash
   poetry run pytest -q 2>&1 | grep -E "warning|Warning" && echo "⚠️  Warnings detected! Fix them before proceeding." && exit 1 || echo "✅ No warnings"
   ```
   *If warnings are detected, investigate and fix them. Common fixes:*
   - Update deprecated APIs (e.g., `autocompletion` → `shell_complete`)
   - Upgrade outdated dependencies (e.g., `pytest-cov`)
   - Fix async test configurations

7. **Handle Failures**
   If the tests fail, analyze the output.
   - If it looks like a missing dependency error, run `poetry install` again or add the missing package with `poetry add <package>`.
   - If it is a code error, fix the code and re-run the tests.