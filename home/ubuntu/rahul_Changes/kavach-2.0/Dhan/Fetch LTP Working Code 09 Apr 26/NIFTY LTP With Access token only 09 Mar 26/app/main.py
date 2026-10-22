from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running this file directly via `python app/main.py`.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.context.app_context import build_app_context
from app.infra.file_writer import print_output_location, write_test_result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch NIFTY/F&O LTP and write external output.")
    parser.add_argument("--symbol", dest="default_symbol", help="Override symbol, e.g. NIFTY")
    parser.add_argument(
        "--output-base", dest="external_output_base", help="Override external output base path"
    )
    parser.add_argument("--timeout", dest="timeout_seconds", type=int, help="Timeout in seconds")
    parser.add_argument("--retries", dest="max_retries", type=int, help="Retry attempts")
    parser.add_argument(
        "--interval", dest="poll_interval_seconds", type=int, help="Polling interval in seconds"
    )
    parser.add_argument("--log-level", dest="log_level", help="Log level, e.g. INFO/DEBUG")
    parser.add_argument("--once", dest="continuous", action="store_false", help="Run once and exit")
    parser.add_argument("--loop", dest="continuous", action="store_true", help="Run continuously")
    parser.set_defaults(continuous=None)
    parser.add_argument(
        "--write-test-result",
        action="store_true",
        help="Also write test_results.txt for runtime verification",
    )
    return parser


def main() -> int:
    logger = None
    try:
        parser = _build_parser()
        args = parser.parse_args()
        overrides = {
            k: v for k, v in vars(args).items() if v is not None and k != "write_test_result"
        }
        ctx = build_app_context(overrides=overrides)
        logger = ctx.logger
        if ctx.settings.continuous:
            logger.info(
                "Continuous mode enabled. Polling every %s seconds. Press Ctrl+C to stop.",
                ctx.settings.poll_interval_seconds,
            )
            while True:
                quote, output_path = ctx.run_once()
                logger.info("Fetched %s LTP %.2f", quote.symbol, quote.ltp)
                print_output_location(output_path)
                if args.write_test_result:
                    write_test_result(ctx.settings.external_output_base, "runtime: PASS")
                time.sleep(ctx.settings.poll_interval_seconds)
        else:
            quote, output_path = ctx.run_once()
            logger.info("Fetched %s LTP %.2f", quote.symbol, quote.ltp)
            if args.write_test_result:
                write_test_result(ctx.settings.external_output_base, "runtime: PASS")
            print_output_location(output_path)
        return 0
    except KeyboardInterrupt:
        if logger:
            logger.info("Stopped by user.")
        return 0
    except Exception as exc:
        if logger:
            logger.exception("Fatal error: %s", exc)
        else:
            print(f"Fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
