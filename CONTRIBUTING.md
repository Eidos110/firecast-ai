# Contributing to FireCast

First off, thank you for considering contributing to FireCast! It's people like you that make FireCast such a great tool.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the issue list as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

* **Use a clear and descriptive title**
* **Describe the exact steps which reproduce the problem**
* **Provide specific examples to demonstrate the steps**
* **Describe the behavior you observed after following the steps**
* **Explain which behavior you expected to see instead and why**
* **Include screenshots and animated GIFs if possible**
* **Include your environment details** (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

* **Use a clear and descriptive title**
* **Provide a step-by-step description of the suggested enhancement**
* **Provide specific examples to demonstrate the steps**
* **Describe the current behavior and the expected behavior**
* **Include screenshots and animated GIFs if applicable**
* **List some other tools or applications where this enhancement exists**

### Pull Requests

* Fill in the required template
* Follow the Python style guide
* Include appropriate test cases
* Update documentation as needed
* End all files with a newline

## Development Setup

1. Fork the repository
2. Clone your fork locally
3. Create a virtual environment
4. Install dependencies: `pip install -r requirements.txt`
5. Create a feature branch: `git checkout -b feature/amazing-feature`
6. Make your changes
7. Add tests for new functionality
8. Run tests: `pytest`
9. Commit your changes with clear messages
10. Push to your fork
11. Open a Pull Request

## Style Guide

### Python Code

* Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
* Use [Black](https://github.com/psf/black) for code formatting
* Use meaningful variable and function names
* Add docstrings to functions and classes
* Add type hints where appropriate

### Commit Messages

* Use clear, descriptive commit messages
* Start with a verb (Add, Fix, Update, etc.)
* Keep the first line to 72 characters or less
* Reference issues and pull requests liberally

### Documentation

* Update README.md if you change functionality
* Add docstrings to new functions and classes
* Include examples for new features
* Document any new dependencies

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_specific.py
```

## Code Review Process

1. At least one maintainer will review your PR
2. Changes may be requested before merge
3. Once approved, your PR will be merged by a maintainer

## Questions?

Feel free to create an issue for any questions about contributing to FireCast.

## Recognition

Contributors will be recognized in:
* README.md contributors section
* Release notes

---

Thank you for contributing to FireCast! 🔥
