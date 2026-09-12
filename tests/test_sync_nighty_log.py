import os
import tempfile
import unittest

from scripts import enforce_config as ec


class SyncNightyLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.appdata = os.path.join(self.tmp.name, "appdata")
        self.diag = os.path.join(self.tmp.name, "diagnostics")
        os.makedirs(self.appdata)
        self.src = os.path.join(self.appdata, "nighty.log")
        self.dst = os.path.join(self.diag, "nighty.log")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, data, mode="wb"):
        with open(self.src, mode) as f:
            f.write(data)

    def _mirror(self):
        ec.sync_nighty_log(self.appdata, diag_dir=self.diag)
        with open(self.dst, "rb") as f:
            return f.read()

    def test_creates_mirror_on_first_sync(self):
        self._write(b"line1\n")
        self.assertEqual(self._mirror(), b"line1\n")

    def test_appends_only_new_tail(self):
        self._write(b"line1\n")
        self._mirror()
        self._write(b"line2\n", mode="ab")
        self.assertEqual(self._mirror(), b"line1\nline2\n")

    def test_noop_when_unchanged(self):
        self._write(b"line1\n")
        self._mirror()
        before = os.stat(self.dst).st_mtime_ns
        self.assertEqual(self._mirror(), b"line1\n")
        self.assertEqual(os.stat(self.dst).st_mtime_ns, before)

    def test_full_resync_after_rotation_truncates_source(self):
        self._write(b"old-and-long\n" * 10)
        self._mirror()
        self._write(b"fresh\n")          # rotation: source now smaller
        self.assertEqual(self._mirror(), b"fresh\n")

    def test_resyncs_when_mirror_diverged_at_same_size(self):
        self._write(b"AAAA\nBBBB\n")
        self._mirror()
        self._write(b"XXXX\nYYYY\n")
        with open(self.dst, "wb") as f:
            f.write(b"AAAA\nBBBB\n")
        self._write(b"NEW1\n", mode="ab")
        self.assertEqual(self._mirror(), b"XXXX\nYYYY\nNEW1\n")

    def test_boundary_window_does_not_detect_divergence_outside_it(self):
        filler = b"F" * (ec.MIRROR_BOUNDARY_CHECK_BYTES * 2)
        self._write(b"HEAD\n" + filler)
        self._mirror()
        with open(self.dst, "r+b") as f:
            f.write(b"BAD!\n")
        self._write(b"NEW1\n", mode="ab")
        mirrored = self._mirror()
        self.assertEqual(mirrored, b"BAD!\n" + filler + b"NEW1\n")

    def test_missing_source_is_noop(self):
        ec.sync_nighty_log(self.appdata, diag_dir=self.diag)
        self.assertFalse(os.path.exists(self.dst))


if __name__ == "__main__":
    unittest.main()
