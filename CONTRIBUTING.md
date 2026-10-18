# Contributing

When contributing to this repository, please first discuss the change you wish to make via issue, email, or any other method with the owners of this repository before making a change.

Please note we have a code of conduct, please follow it in all your interactions with the project.

## Pull Request Process

1. Make sure all unnecessary dependencies are removed.
2. Update the README.md with details of changes if needed.
3. **Version management**: The project uses **calendar versioning** (format: `YYYY.MM.DD`). Version bumps are handled automatically by CI/CD on commits to main - you don't need to manually update versions.
4. You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.

## Code Style & Quality

To ensure code quality, we enforce strict typing and automated testing.

1. **Typing**: All new code must be strictly typed. We use `mypy` for static type checking.
   - Run `poetry run mypy` locally to verify your changes.
   - Ensure your code passes `mypy` without errors before submitting a PR.
   
2. **Testing**: We use `pytest` for testing and `tox` for cross-environment verification.
   - Run `poetry run tox` to validate your changes against supported Python versions.
   - Ensure all tests pass and no regression warnings are introduced.

## Running the Tests

The suite runs offline. It does not start FreeSWITCH or Docker; the ESL peer is a loopback simulator on `127.0.0.1`.

```bash
poetry install
poetry run pytest
poetry run black --check genesis/ tests/ examples/
poetry run mypy genesis/
poetry run tox
```

Suite layout:

- `tests/features/` and `tests/bdd/`: Gherkin scenarios and steps for RingGroup, Session, and Consumer
- `tests/contract/`: ESL wire and protocol boundary checks
- `tests/unit/`: in-memory internals such as the logger, queue, CLI, routing, parser, and reader state machine
- `tests/simulator/`: the loopback ESL peer (it does not import Genesis)
- `tests/references/`: captured and synthetic ESL bytes; see [tests/references/README.md](tests/references/README.md) for provenance and simulator limits

Async tests coordinate with `asyncio.Event`, `asyncio.Condition`, or `asyncio.Future`, bounded by `asyncio.wait_for`. Do not use `asyncio.sleep` or `time.sleep` in tests.
