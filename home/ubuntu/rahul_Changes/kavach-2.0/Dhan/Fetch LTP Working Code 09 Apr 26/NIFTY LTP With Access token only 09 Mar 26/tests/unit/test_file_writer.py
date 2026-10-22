from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.domain.models import LTPQuote
from app.infra.file_writer import write_ltp_output, write_test_result


class TestFileWriter(unittest.TestCase):
    def test_write_ltp_output_to_date_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            quote = LTPQuote(symbol="NIFTY", ltp=22456.25, timestamp="2026-03-09 10:45:00")
            output = write_ltp_output(base_output_path=base, quote=quote)
            self.assertTrue(output.exists())
            self.assertEqual(output.name, "ltp_output.txt")
            self.assertEqual(len(output.parent.name), 10)

    def test_write_test_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            output = write_test_result(base_output_path=base, text="unit: PASS")
            self.assertTrue(output.exists())
            self.assertEqual(output.name, "test_results.txt")


if __name__ == "__main__":
    unittest.main()
