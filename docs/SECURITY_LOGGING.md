# Security & Logging

## LogSanitizer

Auto-masks sensitive data in logs before writing.

### Masked Data Types

| Type | Example Before | Example After |
|------|----------------|---------------|
| API keys (UUID) | `2b6a3146-9b41-4d0a-a3b0-51d294cf2e03` | `xxxx****` |
| Bot tokens | `123456:ABC-DEF` | `xxxx:****` |
| Email | `user@example.com` | `u***@example.com` |
| File paths | `/home/user/app` | `/***` |
| URL params | `?userKey=secret` | `?userKey=****` |

### How It Works

- Initialized in `utils/logging_setup.py`
- Filters all log handlers automatically
- Processes LogRecord before formatting

## Logging Best Practices

### Do

```python
logger.info(f"Got info for dictionary {nsi_id}")
logger.debug(f"API request for {nsi_id}")
```

### Don't

```python
logger.info(f"Request to {url_with_key}")  # Contains API key
logger.exception("Error")  # Full traceback in production
```

### Safe Exception Logging

```python
try:
    risky_operation()
except Exception as e:
    logger.error("Operation failed")
    if logger.isEnabledFor(logging.DEBUG):
        logger.exception("Details")
```

## Log Levels

| Environment | Level | Shows |
|-------------|-------|-------|
| Production | INFO | Events, results, errors (no details) |
| Development | DEBUG | Full details, tracebacks |

## Key Rules

1. Never log keys/tokens explicitly
2. Log only IDs, versions, statuses
3. Use `logger.isEnabledFor(logging.DEBUG)` for detailed errors
4. Test locally with real data to verify masking