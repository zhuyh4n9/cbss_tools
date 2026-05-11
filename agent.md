# CBSS Agent Rules

## Version Management
- Version format: `major.minor.bug_fix`.
- After bug fix: increase `bug_fix`.
- After new feature: increase `minor`.
- Increase `major` only when explicitly requested.

## Coding Principles
- Report bugs found during development.
- Ensure related modules pass unit tests after fixes.
- Report side effects of changes in Chinese.
- Update `changelog/CHANGELOG.md` after changes.
- New modules should follow GoF design principles/patterns.
- Code optimization should follow KISS principle.

## Privacy Rules
- Do not leak critical parameters during development.
- Do not copy private keys into the tool directory.
