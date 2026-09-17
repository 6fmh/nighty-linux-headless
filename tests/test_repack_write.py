from __future__ import annotations

import errno
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nighty_repack", ROOT / "scripts" / "repack.py")
assert SPEC and SPEC.loader
REPACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPACK)

PAYLOAD = b"MZ" + b"\x90" * 4094
OLD_CONTENT = b"stale stub content"


def raising_replace(err):
    def _replace(src, dst):
        raise OSError(err, os.strerror(err))
    return _replace


class WriteOutputTests(unittest.TestCase):
    def test_normal_write_is_atomic_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            how = REPACK.write_output(str(target), PAYLOAD)
            self.assertEqual(how, "atomic")
            self.assertEqual(target.read_bytes(), PAYLOAD)
            self.assertFalse((Path(tmp) / "Nighty_stub.exe.tmp").exists())

    def test_busy_target_falls_back_and_keeps_the_same_inode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            target.write_bytes(OLD_CONTENT)
            inode_before = target.stat().st_ino
            with mock.patch.object(REPACK.os, "replace", raising_replace(errno.EBUSY)):
                how = REPACK.write_output(str(target), PAYLOAD)
            self.assertIn("in-place", how)
            self.assertEqual(target.read_bytes(), PAYLOAD)
            self.assertEqual(target.stat().st_ino, inode_before)
            self.assertFalse((Path(tmp) / "Nighty_stub.exe.tmp").exists())

    def test_cross_device_target_also_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            target.write_bytes(OLD_CONTENT)
            with mock.patch.object(REPACK.os, "replace", raising_replace(errno.EXDEV)):
                how = REPACK.write_output(str(target), PAYLOAD)
            self.assertIn("in-place", how)
            self.assertEqual(target.read_bytes(), PAYLOAD)

    def test_fallback_shrinks_a_larger_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            target.write_bytes(b"X" * (len(PAYLOAD) * 3))
            with mock.patch.object(REPACK.os, "replace", raising_replace(errno.EBUSY)):
                REPACK.write_output(str(target), PAYLOAD)
            self.assertEqual(target.read_bytes(), PAYLOAD)
            self.assertEqual(target.stat().st_size, len(PAYLOAD))

    def test_disk_full_is_raised_not_silently_written_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            target.write_bytes(OLD_CONTENT)
            with mock.patch.object(REPACK.os, "replace", raising_replace(errno.ENOSPC)):
                with self.assertRaises(OSError) as caught:
                    REPACK.write_output(str(target), PAYLOAD)
            self.assertEqual(caught.exception.errno, errno.ENOSPC)
            self.assertEqual(target.read_bytes(), OLD_CONTENT)

    def test_read_only_filesystem_is_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Nighty_stub.exe"
            target.write_bytes(OLD_CONTENT)
            with mock.patch.object(REPACK.os, "replace", raising_replace(errno.EROFS)):
                with self.assertRaises(OSError):
                    REPACK.write_output(str(target), PAYLOAD)
            self.assertEqual(target.read_bytes(), OLD_CONTENT)


if __name__ == "__main__":
    unittest.main()
