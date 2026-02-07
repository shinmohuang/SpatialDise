# Contributing to SpatialDise

Thank you for your interest in contributing.

## Ways to Contribute

- Report bugs and usability issues.
- Propose features or documentation improvements.
- Submit code improvements with tests.

## Before You Start

- Check existing issues and pull requests to avoid duplicate work.
- For non-trivial changes, open an issue first to discuss scope and design.
- Keep pull requests focused and minimal.

## Development Setup

1. Fork and clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
uv sync --group dev
```

4. Run tests:

```bash
pytest -q
```

## Branch and Commit Guidelines

- Create a feature branch from `main`.
- Use clear commit messages (imperative mood).
- Keep commits logically grouped.

## Pull Request Checklist

- Add or update tests for behavior changes.
- Update docs (`README.md` or task docs) when interfaces change.
- Ensure tests pass locally.
- Include a short "what changed / why" summary.

## Code Style

- Prefer readable, explicit code over clever code.
- Keep functions small and focused.
- Avoid unrelated refactors in feature PRs.

## Reporting Bugs

When opening a bug report, include:

- Environment details (OS, Python version, Blender version).
- Reproduction steps.
- Expected behavior vs actual behavior.
- Error logs or screenshots if available.

## Security Issues

Do not report security vulnerabilities publicly.
Please follow the process in `SECURITY.md`.

## License

By contributing, you agree that your contributions will be licensed under the
same license as this repository.
