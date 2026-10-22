# NIFTY LTP Fetcher

Structured, lightweight Python app for fetching NIFTY LTP and writing runtime data to an external date-based path.

## Folder Structure

```text
main.py
app/
  main.py
  bootstrap.py
  config/
    settings.py
  context/
    trading_context.py
  services/
    ltp_service.py
  infra/
    logger.py
    file_writer.py
    clock.py
  domain/
    models.py
    protocols.py
    errors.py
config/
  settings.json
  client_id.txt
  token.txt
tests/
  unit/
  integration/
requirements.txt
pyproject.toml
```

## Runtime Output Policy

All generated files are outside source code, under:

`<external_base_dir>/YYYY-MM-DD/`

Files:
- `ltp_output.txt`
- `logs.txt`
- `test_results.txt` (when tests/scripts write it)

## Run

```bash
python main.py
```

By default, runtime runs in continuous mode and fetches LTP every `runtime.poll_interval_seconds` (default `10`) from `config/settings.json`.

Run once and exit:

```bash
python main.py --once
```

CLI overrides:

```bash
python main.py --symbol NIFTY --timeout 20 --retries 2 --log-level INFO --write-test-result
```

## Unit Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Binary Artifacts

Local runtime binaries (virtual environment, cache binaries) should not stay in the project source folder. Keep virtual environments outside this directory and recreate them when needed.
