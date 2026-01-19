---
description: Create a Pull Request respecting the semantic versioning rules of the project.
---

# Create Pull Request Workflow

This workflow guides you through creating a Pull Request while respecting the project's versioning logic (checking for `(major)`, `(minor)` in commit messages).

1. **Run Full Validation (Tox)**
   Before creating a PR, run the full validation suite (tests + types) across all supported environments to prevent CI failures.
   
   Ensure necessary python versions are available (using asdf if needed, e.g. `asdf set python 3.10.19 3.11.9 3.12.4`).
   ```bash
   poetry run tox
   ```
   *Fix any errors before proceeding.*

2. **Determine Version Bump**
   Ask the user what kind of version bump this change represents:
   - **Major**: Breaking changes.
   - **Minor**: New features (backward compatible).
   - **Patch**: Bug fixes (backward compatible).

3. **Stage Changes**
   // turbo
   Stage all modified files.
   ```bash
   git add .
   ```

4. **Commit with Version Tag**
   Construct the commit message based on the user's choice from step 2. You MUST include the tag in the message if it's Major or Minor.

   - **If Major**: `git commit -m "feat(major): <message>"` (or just include `(major)` anywhere in the message)
   - **If Minor**: `git commit -m "feat(minor): <message>"` (or just include `(minor)` anywhere in the message)
   - **If Patch**: `git commit -m "fix: <message>"` (no specific tag needed, patch is default)

   *Ask the user for the specific commit message content.*

5. **Push Branch**
   Push the current branch to origin.
   ```bash
   git push origin HEAD
   ```

6. **Create Pull Request**
   Create the PR using GitHub CLI with a temporary file for the body to avoid formatting issues.

   First, ask the user for the PR title and body.
   Then, create a temporary file with the body content:
   ```bash
   echo "PR Body Content" > pr_body.txt
   ```

   Finally, create the PR using the `--body-file` flag:
   ```bash
   gh pr create --title "Your PR Title" --body-file pr_body.txt
   ```
   *After the PR is created, remove the temporary file:*
   ```bash
   rm pr_body.txt
   ```