# Everlight Agents

This document provides conventions for working with the everlight-agents codebase.

## Local Development

To set up the project locally, first install the dependencies using `uv`:

```bash
uv pip install -r requirements.txt
```

To run the app in development mode, use the following command:

```bash
uvicorn main:app --reload
```

## Linting and Formatting

This project uses `ruff` for linting and formatting. To lint the code, run:

```bash
ruff check .
```

To format the code, run:

```bash
ruff format .
```

## Testing

This project uses `pytest` for testing. To run all tests, use the following command:

```bash
pytest
```

To run a specific test, use the following command:

```bash
pytest path/to/test_file.py::test_name
```

## Code Style

- **Imports**: Use `isort` compatible import ordering.
- **Typing**: Use type hints for all function signatures.
- **Naming**: Use `snake_case` for variables and functions. Use `PascalCase` for classes.
- **Error Handling**: Use `try...except` blocks for code that may raise exceptions.
- **Docstrings**: Use Google-style docstrings for all public modules, functions, classes, and methods.
