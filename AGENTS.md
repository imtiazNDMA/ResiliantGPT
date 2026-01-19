# Agent Guidelines for ResilienceGPT

## Build/Test Commands
- **Install dependencies**: `uv sync`
- **Run application**: `uv run app.py`
- **Run all tests**: `python -m pytest tests/`
- **Run single test**: `python -m pytest tests/test_file.py`
- **Format code**: `black .`
- **Type check**: `mypy .`

## Code Style Guidelines
- **Imports**: Standard library first, then third-party, then local. Use absolute imports.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants, `_leading_underscore` for private methods.
- **Types**: Use type hints extensively. Import from `typing`. Use `Optional` for nullable types.
- **Error Handling**: Specific exceptions in try/except. Log with logging module. No bare except.
- **Formatting**: PEP 8, 4 spaces indentation, 88 char lines (Black), double quotes for strings.
- **Comments**: Descriptive names preferred. Comments for complex logic only. Keep concise.

## Continue Rules
- Follow project guide in `.continue/rules/CONTINUE.md` for development workflow and architecture.</content>
<parameter name="filePath">G:/Hizbullah/ResilienceGPT/AGENTS.md