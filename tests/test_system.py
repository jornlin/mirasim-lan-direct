import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mld import system  # noqa: E402


BINARY = "/Applications/Mirasim.app/Contents/MacOS/Mirasim"
HELPERS = "\n".join([
    BINARY + " --max-old-space-size=4096 /Applications/Mirasim.app/Contents/Resources/server.cjs serve --port 4970",
    BINARY + " /Applications/Mirasim.app/Contents/Resources/screen-lane.cjs",
    BINARY + " /Applications/Mirasim.app/Contents/Resources/gui/dist/entries/cli.cjs bridge",
])


class SystemTests(unittest.TestCase):
    def test_darwin_main_process_ignores_helpers(self):
        self.assertTrue(system._darwin_main_running(BINARY, BINARY + "\n" + HELPERS))
        self.assertFalse(system._darwin_main_running(BINARY, HELPERS))


if __name__ == "__main__":
    unittest.main()
