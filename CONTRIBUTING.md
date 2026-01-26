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
