# Repository agent rules

This is a public product repository. Keep private planning and product reasoning outside this repository.

- Never commit local agent state, QA captures, generated artifacts, machine-specific paths, usernames, credentials, or private prompts/images.
- Treat `.agents/`, `.codex/`, `.codex-qa-*`, `.codebase-memory/`, `.qa-*`, `.superpowers/`, `docs/plans/`, and `docs/qa/` as local-only.
- Stage explicit paths only. Never use `git add .` or `git add -A`.
- Before every commit, inspect `git status --short`, `git diff --cached --name-status`, and `git diff --cached`.
- Before every push, inspect `git diff --name-status origin/main...HEAD`.
- Preserve unrelated user changes and local QA artifacts.
- Commit only product code, user-facing documentation, tests, and required release files for the current task.
