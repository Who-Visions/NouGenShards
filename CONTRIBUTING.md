# Contributing to NouGenShards

Welcome! We are excited to have you contribute to the local memory layer for AI agents.

## 🛠️ Development Setup

### 1. Clone the repo
```bash
git clone https://github.com/Who-Visions/NouGenShards.git
cd NouGenShards
```

### 2. Environment
We recommend using a virtual environment:
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Unix
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -e .
```

Deployments (Docker/Space, CI) install from the compiled lockfile instead for
fully reproducible builds. If you change dependencies in `pyproject.toml`,
regenerate it:
```bash
uv pip compile --universal pyproject.toml -o requirements.txt
```

## 🧪 Testing
We maintain a 100% pass rate requirement. Before submitting a PR, run the full suite
(no PYTHONPATH setup needed — pytest picks up `src/` from `pyproject.toml`):
```bash
python -m pytest tests
```

## 📐 Standards
- **Clean Code**: Follow PEP 8 and "Clean Code" principles.
- **Type Hints**: All new functions should have Python type hints.
- **Docstrings**: Provide Google-style docstrings for modules and public functions.
- **Lint**: `ruff check src tests` must pass (enforced in CI; config in `ruff.toml`).

## 🚀 Pull Request Process
1. Create a feature branch.
2. Implement your changes with tests.
3. Ensure all tests pass.
4. Update `CHANGELOG.md`.
5. Submit the PR for review.

> 🇭🇹 This project is maintained by Who Visions LLC.
