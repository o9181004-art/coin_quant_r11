# Contributing to Coin Quant R11

Thank you for your interest in contributing to Coin Quant R11! This document provides guidelines for contributing to the project.

## Getting Started

### Prerequisites
- Python 3.11 or higher
- Git
- Virtual environment (recommended)

### Setup Development Environment

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/coin_quant_r11.git
   cd coin_quant_r11
   ```

3. Create virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

4. Install package in editable mode:
   ```bash
   pip install -e .
   ```

5. Run validation tests:
   ```bash
   python validate.py
   ```

## Development Guidelines

### Code Style
- Follow PEP 8 style guidelines
- Use type hints where appropriate
- Write docstrings for all public functions and classes
- Keep functions small and focused

### Package Structure
- Maintain the established package structure
- Use absolute imports (`from coin_quant...`)
- Keep shared utilities in `coin_quant.shared`
- Service-specific code in respective packages

### Testing
- Write tests for new features
- Ensure all tests pass before submitting
- Use the existing test framework
- Test both success and failure cases

### Documentation
- Update README.md for user-facing changes
- Update MIGRATION.md for breaking changes
- Update CHANGELOG.md for all changes
- Write clear commit messages

## Submitting Changes

### Pull Request Process

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and test them:
   ```bash
   python validate.py
   python test_smoke.py
   ```

3. Commit your changes:
   ```bash
   git add .
   git commit -m "Add: brief description of changes"
   ```

4. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

5. Create a Pull Request on GitHub

### Commit Message Format

Use the following format for commit messages:

```
type: brief description

Longer description if needed

Fixes #issue_number
```

Types:
- `Add:` - New features
- `Fix:` - Bug fixes
- `Update:` - Updates to existing features
- `Remove:` - Removal of features
- `Refactor:` - Code refactoring
- `Docs:` - Documentation updates
- `Test:` - Test updates

### Pull Request Guidelines

- Provide a clear description of changes
- Reference any related issues
- Ensure all tests pass
- Update documentation as needed
- Keep PRs focused and atomic

## Code Review Process

### Review Criteria
- Code follows style guidelines
- Tests are included and pass
- Documentation is updated
- Changes are well-tested
- No breaking changes without migration path

### Review Process
1. Automated tests must pass
2. At least one maintainer review required
3. Address all feedback before merging
4. Maintainer will merge after approval

## Issue Reporting

### Bug Reports
When reporting bugs, include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages and logs

### Feature Requests
For feature requests, include:
- Use case description
- Proposed solution
- Alternative solutions considered
- Impact on existing functionality

## Development Setup

### Running Services Locally

1. Start services in order:
   ```bash
   python launch.py feeder
   python launch.py ares
   python launch.py trader
   ```

2. Monitor health files:
   ```bash
   # Check service health
   cat shared_data/health/feeder.json
   cat shared_data/health/ares.json
   cat shared_data/health/trader.json
   ```

### Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python launch.py feeder
```

### Memory Layer Testing

Test memory layer components:
```bash
python -c "from coin_quant.memory.client import MemoryClient; client = MemoryClient(); print('Memory layer OK' if client.verify_chain()[0] else 'Memory layer ERROR')"
```

## Release Process

### Version Numbering
- Follow Semantic Versioning (SemVer)
- Major: Breaking changes
- Minor: New features (backward compatible)
- Patch: Bug fixes (backward compatible)

### Release Steps
1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release tag
4. Build and publish package
5. Update documentation

## Community Guidelines

### Code of Conduct
- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's mission

### Getting Help
- Check existing documentation
- Search closed issues
- Ask questions in discussions
- Provide clear problem descriptions

## License

By contributing to Coin Quant R11, you agree that your contributions will be licensed under the MIT License.

## Thank You

Thank you for contributing to Coin Quant R11! Your contributions help make the project better for everyone.
