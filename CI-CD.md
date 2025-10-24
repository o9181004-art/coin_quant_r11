# Coin Quant R11 - CI/CD Pipeline

This document describes the CI/CD pipeline configuration for Coin Quant R11.

## GitHub Actions Workflow

### Main CI/CD Pipeline

**File:** `.github/workflows/ci-cd.yml`

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: [3.11]

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov flake8 mypy
    
    - name: Lint with flake8
      run: |
        flake8 src/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 src/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
    
    - name: Type check with mypy
      run: |
        mypy src/ --ignore-missing-imports --no-strict-optional
    
    - name: Test with pytest
      run: |
        pytest test_smoke.py -v --cov=src/ --cov-report=xml
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella

  build:
    needs: test
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install build dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: |
        python -m build
    
    - name: Upload build artifacts
      uses: actions/upload-artifact@v3
      with:
        name: dist
        path: dist/

  deploy:
    needs: build
    runs-on: windows-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Download build artifacts
      uses: actions/download-artifact@v3
      with:
        name: dist
        path: dist/
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: |
        twine upload dist/*
```

### Smoke Test Pipeline

**File:** `.github/workflows/smoke-test.yml`

```yaml
name: Smoke Tests

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:

jobs:
  smoke-test:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run smoke tests
      run: |
        python test_smoke.py
    
    - name: Check import cycles
      run: |
        python -c "
        import sys
        sys.path.insert(0, 'src')
        try:
            from coin_quant import feeder, ares, trader, memory
            print('✅ No import cycles detected')
        except ImportError as e:
            print(f'❌ Import cycle detected: {e}')
            sys.exit(1)
        "
```

## Pre-commit Hooks

### Pre-commit Configuration

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: debug-statements

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=127, --max-complexity=10]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports, --no-strict-optional]

  - repo: local
    hooks:
      - id: smoke-test
        name: Smoke Test
        entry: python test_smoke.py
        language: system
        pass_filenames: false
        always_run: true
```

## Tox Configuration

### Multi-Environment Testing

**File:** `tox.ini`

```ini
[tox]
envlist = py311, lint, typecheck, smoke
isolated_build = True

[testenv]
deps =
    pytest>=7.0.0
    pytest-cov>=4.0.0
    pytest-mock>=3.10.0
commands = pytest test_smoke.py -v --cov=src/ --cov-report=term-missing

[testenv:lint]
deps =
    flake8>=6.0.0
    black>=23.0.0
commands =
    black --check src/
    flake8 src/ --max-line-length=127 --max-complexity=10

[testenv:typecheck]
deps =
    mypy>=1.3.0
commands = mypy src/ --ignore-missing-imports --no-strict-optional

[testenv:smoke]
deps =
    -r requirements.txt
commands = python test_smoke.py
```

## Code Quality Tools

### Flake8 Configuration

**File:** `setup.cfg`

```ini
[flake8]
max-line-length = 127
max-complexity = 10
exclude = 
    .git,
    __pycache__,
    .venv,
    venv,
    build,
    dist,
    *.egg-info
ignore = 
    E203,  # whitespace before ':'
    W503,  # line break before binary operator
    E501   # line too long (handled by black)
```

### MyPy Configuration

**File:** `mypy.ini`

```ini
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False
ignore_missing_imports = True
no_strict_optional = True
show_error_codes = True

[mypy-tests.*]
ignore_errors = True
```

## Coverage Configuration

### Coverage Settings

**File:** `.coveragerc`

```ini
[run]
source = src/
omit = 
    */tests/*
    */test_*
    */__pycache__/*
    */venv/*
    */env/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    if self.debug:
    if settings.DEBUG
    raise AssertionError
    raise NotImplementedError
    if 0:
    if __name__ == .__main__.:
    class .*\bProtocol\):
    @(abc\.)?abstractmethod
```

## Security Scanning

### Security Workflow

**File:** `.github/workflows/security.yml`

```yaml
name: Security Scan

on:
  schedule:
    - cron: '0 2 * * 1'  # Weekly on Monday
  workflow_dispatch:

jobs:
  security:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install safety bandit
    
    - name: Run safety check
      run: |
        safety check --json --output safety-report.json
    
    - name: Run bandit security scan
      run: |
        bandit -r src/ -f json -o bandit-report.json
    
    - name: Upload security reports
      uses: actions/upload-artifact@v3
      with:
        name: security-reports
        path: |
          safety-report.json
          bandit-report.json
```

## Performance Testing

### Performance Workflow

**File:** `.github/workflows/performance.yml`

```yaml
name: Performance Tests

on:
  schedule:
    - cron: '0 3 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  performance:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest-benchmark memory-profiler
    
    - name: Run performance tests
      run: |
        python -m pytest test_performance.py --benchmark-only --benchmark-save=performance
    
    - name: Upload performance results
      uses: actions/upload-artifact@v3
      with:
        name: performance-results
        path: .benchmarks/
```

## Deployment

### Release Workflow

**File:** `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: windows-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: 3.11
    
    - name: Install build dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: |
        python -m build
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: |
        twine upload dist/*
    
    - name: Create GitHub Release
      uses: actions/create-release@v1
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        tag_name: ${{ github.ref }}
        release_name: Release ${{ github.ref }}
        draft: false
        prerelease: false
```

## Local Development

### Development Setup

```bash
# Install pre-commit hooks
pre-commit install

# Run all checks locally
tox

# Run specific checks
tox -e lint
tox -e typecheck
tox -e smoke

# Run tests with coverage
pytest test_smoke.py --cov=src/ --cov-report=html
```

### VS Code Configuration

**File:** `.vscode/settings.json`

```json
{
    "python.defaultInterpreterPath": "./venv/Scripts/python.exe",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
        "test_smoke.py"
    ],
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/venv": true,
        "**/.pytest_cache": true
    }
}
```

## Monitoring

### CI/CD Metrics

- **Build Success Rate**: Target >95%
- **Test Coverage**: Target >80%
- **Build Time**: Target <10 minutes
- **Security Issues**: Zero critical/high severity
- **Performance Regression**: <5% degradation

### Alerts

- Build failures
- Security vulnerabilities
- Performance regressions
- Coverage drops
- Dependency updates
