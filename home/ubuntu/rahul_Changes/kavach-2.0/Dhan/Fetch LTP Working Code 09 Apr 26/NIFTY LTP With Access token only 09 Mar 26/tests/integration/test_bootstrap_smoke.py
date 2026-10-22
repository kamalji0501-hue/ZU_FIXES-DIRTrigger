from __future__ import annotations

import unittest


class TestBootstrapSmoke(unittest.TestCase):
    def test_package_imports(self) -> None:
        import app.main  # noqa: F401
        import app.bootstrap  # noqa: F401


if __name__ == "__main__":
    unittest.main()
