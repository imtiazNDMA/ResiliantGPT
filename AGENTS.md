# Agent Guidelines for ChatbotARK

## Build/Test Commands
- **Install dependencies**: `uv sync`
- **Run application**: `uv run app.py`
- **Run all tests**: `python -m pytest tests/`
- **Run single test**: `python tests/test_file.py`
- **Format code**: `black .`
- **Type check**: `mypy .`

## Code Style Guidelines

### Imports
- Standard library imports first
- Third-party imports second
- Local imports last
- Use absolute imports for local modules

### Naming Conventions
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_CASE`
- Private methods: `_leading_underscore`

### Error Handling
- Use try/except blocks with specific exceptions
- Log errors using the logging module
- Avoid bare except clauses

### Types
- Use type hints where possible
- Import from `typing` module when needed
- Use `Optional` for nullable types

### Formatting
- Follow PEP 8 style guide
- Use 4 spaces for indentation
- Line length: 88 characters (Black default)
- Use double quotes for strings

### Comments & Documentation
- Use descriptive variable/function names
- Add comments for complex logic
- Keep comments concise and clear</content>
<parameter name="filePath">G:/Hizbullah/ChatbotARK/AGENTS.md