# GitHub Copilot Instructions for mozilla/bugbot

## Project Overview

BugBot is a Bugzilla management bot used by Mozilla release management to:
- Send automated emails to Firefox developers
- Query bugzilla.mozilla.org database
- Notify release managers about potential issues
- Auto-fix certain categories of issues
- Manage triage rotations and component assignments

The bot includes numerous "rules" that check bug states and take actions (email, update bugs, etc.).

## Development Environment

### Setup
- This project uses **uv** for Python environment management (not pip or virtualenv directly)
- Python version: 3.10 - 3.12 (see `pyproject.toml`)
- Install dependencies: `uv sync`
- Run scripts: `uv run -m bugbot.rules.<rule_name>`

### Configuration
- Config files are in `configs/` directory (not committed)
- `configs/config.json` contains API keys for Bugzilla, LDAP, SMTP, etc.
- See README.rst for configuration details

## Code Style and Quality

### Linting and Formatting
- **ruff**: Primary linter and formatter
- **pre-commit**: Used for automated checks before commits
- Run formatters: `uv run ruff format .`
- Run linter: `uv run ruff check . --fix`
- Install pre-commit hooks: `uv tool install pre-commit && pre-commit install`

### Code Style Guidelines
- Follow PEP 8 conventions
- Use type hints where appropriate (mypy is configured)
- All source files must include the Mozilla Public License header:
  ```python
  # This Source Code Form is subject to the terms of the Mozilla Public
  # License, v. 2.0. If a copy of the MPL was not distributed with this file,
  # You can obtain one at http://mozilla.org/MPL/2.0/.
  ```

### Pre-commit Hooks
The project uses multiple pre-commit hooks:
- `djlint`: For Jinja2 template files
- `ruff`: For Python formatting and linting
- `mypy`: For type checking
- `codespell`: For spell checking
- Standard hooks: check-ast, check-yaml, check-json, trailing-whitespace, etc.

## Testing

### Test Framework
- Uses Python's built-in `unittest` framework
- Tests are in the `tests/` directory
- Coverage tracking with `coverage`

### Running Tests
- Run all tests: `uv run coverage run --branch --source ./bugbot -m unittest -v`
- Run specific test: `uv run python -m unittest tests.test_<name>`
- Tox is configured for testing across Python 3.10, 3.11, and 3.12

### Test Structure
- Mock data is in `tests/mocks/` and `tests/data/`
- Tests use `responses` library for mocking HTTP requests
- Tests should cover both normal and edge cases

## Architecture and Key Patterns

### BzCleaner Base Class
- Located in `bugbot/bzcleaner.py`
- Base class for all bug-checking rules
- Key attributes:
  - `no_bugmail`: Use account that doesn't trigger bugmail for changes
  - `normal_changes_max`: Maximum allowed changes to prevent accidents
  - `dryrun`: Test mode without making actual changes

### Rules System
- Rules are in `bugbot/rules/` directory
- Each rule is a Python module that checks for specific bug patterns
- Rules inherit from `BzCleaner`
- Rules can:
  - Query bugs using Bugzilla REST API
  - Send emails via templates in `templates/`
  - Update bug fields
  - Add comments to bugs

### Common Components
- `bugbot/utils.py`: Utility functions
- `bugbot/mail.py`: Email sending functionality
- `bugbot/people.py`: Mozilla people/IAM integration
- `bugbot/cache.py`: Caching layer for API responses
- `bugbot/db.py`: Database operations (SQLAlchemy)
- `bugbot/round_robin.py`: Triage rotation management

### Templates
- Jinja2 templates in `templates/` directory
- Used for email bodies and bug comments
- Separate templates for plain text (.txt) and HTML (.html)

## Common Workflows

### Adding a New Rule
1. Create new file in `bugbot/rules/`
2. Inherit from `BzCleaner` or appropriate base class
3. Implement required methods (typically `get_bugs()` and `handle_bugs()`)
4. Add email templates if needed in `templates/`
5. Add tests in `tests/rules/`
6. Document the rule on Mozilla wiki

### Running Rules
- Dry run: `uv run -m bugbot.rules.<rule_name> --dryrun`
- Production: `uv run -m bugbot.rules.<rule_name>`
- With specific dates: `--production-date=YYYY-MM-DD`

### Database Migrations
- Uses Alembic for database migrations
- Migration files in `bugbot/db_migrations/versions/`
- Run migrations: `alembic upgrade head`

## External Dependencies

### APIs Used
- Bugzilla REST API (libmozdata library)
- Mozilla IAM/Phonebook
- Google Cloud BigQuery
- Google Sheets (for triage rotations)
- Phabricator (historical)

### Key Libraries
- `libmozdata`: Mozilla's Bugzilla client library
- `Jinja2`: Template engine
- `SQLAlchemy`: Database ORM (version 1.3.24)
- `requests`: HTTP client
- `sentry-sdk`: Error tracking

## Special Considerations

### Security
- API keys and credentials are in `configs/config.json` (not in repo)
- No credentials should be committed to the repository
- Use `SilentBugzilla` class for changes that shouldn't trigger bugmail

### Performance
- Use caching (`bugbot/cache.py`) for repeated API calls
- Be mindful of Bugzilla API rate limits
- Large queries should use appropriate pagination

### Error Handling
- Sentry is configured for error tracking
- Uncaught exceptions are logged and sent to Sentry
- Rules should handle edge cases gracefully

## CI/CD

### Taskcluster
- CI configuration in `.taskcluster.yml`
- Runs on TaskCluster (Mozilla's CI system)
- Tests run automatically on pull requests

### Cron Jobs
- Production runs via cron (see README.rst)
- Hourly, daily, and weekday schedules
- Logs are important for monitoring

## Documentation

- Primary documentation: README.rst
- Mozilla wiki: https://wiki.mozilla.org/BugBot
- API documentation: Bugzilla REST API wiki
- Triage rotations: Google Sheets (linked in README)

## Common Pitfalls to Avoid

1. **Don't commit config.json**: It contains secrets
2. **Test with --dryrun first**: Always dry run before production
3. **Respect normal_changes_max**: Prevents accidental mass updates
4. **Include Mozilla license header**: Required in all source files
5. **Use uv, not pip**: Project uses uv for dependency management
6. **Check pre-commit**: Run before committing to avoid CI failures
7. **Mind the database**: SQLAlchemy 1.3.24 is old, use appropriate syntax

## Helpful Commands

```bash
# Setup environment
uv sync

# Run a rule (dry run)
uv run -m bugbot.rules.stalled --dryrun

# Run tests
uv run coverage run --branch --source ./bugbot -m unittest -v

# Format code
uv run ruff format .

# Lint code
uv run ruff check . --fix

# Type check
uv run mypy bugbot

# Run pre-commit hooks
pre-commit run --all-files

# Database migrations
alembic upgrade head
```
