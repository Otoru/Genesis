# Test Timeout Rule

## Context
When running tests, it is critical to prevent the agent from hanging indefinitely if a test blocks.

## Rule
- **Timeout is Mandatory**: Whenever running tests using `pytest`, you MUST enforce a timeout.
  - Install `pytest-timeout` if needed or use the system `timeout` command (e.g., `timeout 30s pytest ...`).
  - **Reason**: To prevent the agent from getting stuck on hanging tests/loops.
