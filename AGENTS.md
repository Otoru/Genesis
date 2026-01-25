# AGENTS.md

Guidance for AI assistants working on the Genesis project.

## Overview

Genesis is an async Python library for FreeSWITCH Event Socket Layer (ESL) integration. Key components:

- `Inbound`: ESL client (app connects to FreeSWITCH)
- `Outbound`: ESL server (FreeSWITCH connects to app)
- `Consumer`: Event consumption with decorators
- `Session`: Call session in outbound mode
- `Channel`: Channel abstraction
- `Protocol`: Base class for ESL clients

## Development Tools

### Poetry

Poetry manages dependencies and virtual environments. Always use Poetry commands:

```bash
# Install dependencies
poetry install

# Add a dependency
poetry add package-name

# Add a dev dependency
poetry add --group dev package-name

# Run commands in the Poetry environment
poetry run <command>

# Activate shell
poetry shell
```

**Important**: Never use `pip install` directly. Always use `poetry add` or edit `pyproject.toml` and run `poetry lock --no-update`.

### Type Checking with mypy

All code must be strictly typed and pass mypy validation:

```bash
# Check types
poetry run mypy

# Check specific file
poetry run mypy genesis/channel.py
```

**Rules**:
- All functions, methods, and variables must have type hints
- Use `typing` module types (`List[str]`, `Dict[str, Any]`, `Optional[str]`)
- Use types from `genesis.types` when available (e.g., `HangupCause`)
- Fix all mypy errors before committing

**Configuration**: See `[tool.mypy]` in `pyproject.toml`:
- Checks `genesis/` directory
- `ignore_missing_imports = false` (strict)
- `check_untyped_defs = true`
- `no_implicit_optional = true`

### Testing

#### pytest

Run tests with pytest:

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_channel.py

# Run with verbose output
poetry run pytest -vvv

# Run specific test
poetry run pytest tests/test_channel.py::test_channel_state
```

**Test Structure**:
- Tests in `tests/` directory
- Fixtures in `tests/conftest.py`
- Mocks/stubs in `tests/doubles.py`
- Test data in `tests/payloads.py`
- Async tests use `pytest.mark.asyncio` or `asyncio_mode = "auto"`

**Configuration**: See `[tool.pytest.ini_options]` in `pyproject.toml`:
- `asyncio_mode = "auto"` (auto-detect async tests)
- `timeout = 10` (via pytest-timeout)
- `addopts = "-vvv -x --full-trace --timeout=10"`

#### tox

Validate across Python versions (3.10, 3.11, 3.12):

```bash
# Run tests on all Python versions
poetry run tox

# Run specific environment
poetry run tox -e py310

# List environments
poetry run tox list
```

**Always run tox before PRs** to ensure compatibility.

### Code Formatting

Use Black for formatting:

```bash
# Format code
poetry run black genesis/ tests/

# Check formatting (no changes)
poetry run black --check genesis/ tests/
```

**Version constraint**: `>=22.1,<25.0` (see `pyproject.toml`)

## Code Standards

### Type Hints

```python
from typing import Optional, List, Dict, Any
from genesis.types import HangupCause

async def process_event(
    event: ESLEvent,
    channels: List[str],
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[HangupCause]:
    ...
```

### Import Organization

**Rules**:
- All imports must be at the top of the file
- Native Python imports first (standard library)
- Library imports second (third-party and project imports)
- Separate groups with a blank line

**Example**:

```python
import asyncio
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.table import Table

from genesis.types import HangupCause
from genesis.channel import Channel
from genesis.consumer import Consumer
```

**Order**:
1. Standard library imports (sorted by length)
2. Blank line
3. Third-party library imports (sorted by length)
4. Blank line (if project imports follow)
5. Project imports (sorted by length)

### Async Patterns

- Always use `async/await` for I/O operations
- Use `async with` for context managers
- Handle `CancelledError` appropriately
- Use `asyncio.create_task()` for concurrent operations

### Naming Conventions

- Classes: `PascalCase` (e.g., `ESLEvent`, `Session`)
- Functions/Methods: `snake_case` (e.g., `send_command`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `TRACE_LEVEL_NUM`)
- Modules: `snake_case` (e.g., `consumer.py`)

## CI/CD Workflows

### GitHub Actions

The project uses a consolidated CI/CD pipeline in `.github/workflows/main.yml`:

**Main Workflow** (`main.yml`):
- **Tests**: Runs on all PRs and pushes to main (Python 3.10, 3.11, 3.12)
  - Linter (Black)
  - Type checker (Mypy)
  - Unit tests (pytest)
- **Update Contributors**: Updates README.md contributors list (only on push to main)
- **Bump Version**: Automatically updates version to calendar format `YYYY.MM.DD` (only on push to main)
- **Build & Deploy Docs**: Builds and deploys documentation to GitHub Pages (only on push to main)

**PyPI Workflow** (`pypi.yml`):
- Publishes to PyPI when a release is published

**Important Notes**:
- The workflow automatically skips execution when commits are made by the bot (prevents infinite loops)
- Version bumping happens automatically using calendar format (year.month.day)
- All jobs run in sequence: tests → contributors → version → docs

### Versioning

The project uses **calendar versioning** (not semantic versioning):
- Format: `YYYY.MM.DD` (e.g., `2026.01.24`)
- Automatically updated on each commit to main
- No manual version bumps needed
- Version is set in `pyproject.toml`

## Pre-PR Checklist

Before submitting a PR, ensure:

1. **Types**: `poetry run mypy` passes with no errors
2. **Tests**: `poetry run pytest` passes
3. **Multi-version**: `poetry run tox` passes on all Python versions
4. **Formatting**: `poetry run black --check` passes
5. **Dependencies**: No unnecessary dependencies added
6. **Documentation**: 
   - README.md updated if needed
   - **All language versions updated** (en, pt, ko) if documentation changed
7. **Version**: Version is automatically managed by CI/CD (calendar format)

## Python Versions

Supported: Python 3.10, 3.11, 3.12

Constraint: `>=3.10,<4.0` (see `pyproject.toml`)

## Resources

- Documentation: https://otoru.github.io/Genesis/
- Repository: https://github.com/Otoru/Genesis
- PyPI: https://pypi.org/project/genesis/
