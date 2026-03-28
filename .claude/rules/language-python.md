# Python Standards

- Python 3.12+ required
- Lint/format with `ruff` (replaces black, isort, flake8)
- Use `pathlib.Path` over `os.path`
- Type hints on all public API functions and methods
- Use `dataclasses` or `pydantic` for structured data, not raw dicts
- Virtual envs: prefer `uv` over pip for speed
