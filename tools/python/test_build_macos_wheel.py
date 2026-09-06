"""Portable adversarial checks for the offline macOS wheel packager."""
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location(
    "wheel_builder", Path(__file__).with_name("build_macos_wheel.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class MachOAdmissionTests(unittest.TestCase):
    def inspect(self, dependency="/usr/lib/libSystem.B.dylib", minimum="11.0",
                architecture="arm64", target_platform="1"):
        def output(arguments):
            kind = arguments[:2]
            if kind == ["lipo", "-archs"]:
                return architecture + "\n"
            if kind == ["otool", "-D"]:
                return "staged:\n@rpath/libsolver.dylib\n"
            if kind == ["otool", "-L"]:
                return ("staged:\n\t@rpath/libsolver.dylib (compatibility version 0.0.0, current version 0.0.0)\n"
                        + "\t" + dependency + " (compatibility version 1.0.0, current version 1.0.0)\n")
            if kind == ["otool", "-l"]:
                return ("Load command 0\n      cmd LC_BUILD_VERSION\n cmdsize 32\n platform "
                        + target_platform + "\n    minos " + minimum + "\n      sdk 26.0\n")
            self.fail("unexpected inspection command")
        with patch.object(builder, "command", side_effect=output), \
                patch.object(builder.platform, "machine", return_value="arm64"):
            return builder.inspect_library(Path("private-staging/library"))

    def test_system_dependencies_and_deployment_target(self):
        for dependency in ("/usr/lib/libSystem.B.dylib", "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation"):
            tag, detail = self.inspect(dependency)
            self.assertEqual(tag, "macosx_11_0_arm64")
            self.assertEqual(detail["system_dependencies"], [dependency])

    def test_prefix_traversal_is_rejected(self):
        for dependency in ("/usr/lib/../../Users/example/libx.dylib",
                           "/System/Library/../../Users/example/libx.dylib",
                           "/usr/lib/./libx.dylib", "@rpath/libx.dylib",
                           "/usr/library/libx.dylib", "/tmp/libx.dylib"):
            with self.subTest(dependency=dependency), self.assertRaisesRegex(ValueError, "non-system"):
                self.inspect(dependency)

    def test_newer_minor_binary_is_not_retagged(self):
        for minimum in ("15.7", "11.0.1", "10.15", "11.0.0.1"):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                self.inspect(minimum=minimum)

    def test_platform_and_architecture_must_match(self):
        for kwargs in (dict(architecture="x86_64"), dict(architecture="arm64 x86_64"),
                       dict(target_platform="2")):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.inspect(**kwargs)

    def test_inspection_uses_captured_bytes_during_source_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "build-output"
            staged = Path(temporary) / "private-copy"
            source.write_bytes(b"captured binary A")
            def inspect(path):
                source.write_bytes(b"replacement binary B")
                self.assertEqual(path, staged)
                self.assertEqual(path.read_bytes(), b"captured binary A")
                return "macosx_11_0_arm64", {"inspected": "A"}
            with patch.object(builder, "inspect_library", side_effect=inspect):
                binary, tag, detail = builder.stage_library(source, staged)
            self.assertEqual(binary, staged.read_bytes())
            self.assertNotEqual(binary, source.read_bytes())
            self.assertEqual(detail, {"inspected": "A"})
            self.assertEqual(tag, "macosx_11_0_arm64")


class WheelIntegrityTests(unittest.TestCase):
    binary = b"captured solver"
    binary_name = "gecode_optimize/_native/" + builder.ENTRY
    record_name = "gecode_optimize-0.1.dist-info/RECORD"

    def archive(self, *, extra=None, omit_record=None, bad_digest=False,
                bad_size=False, duplicate_record=False, altered_binary=False):
        files = {self.binary_name: self.binary, "gecode_optimize/__init__.py": b"# package\n"}
        files.update(extra or {})
        rows = []
        for name, data in files.items():
            digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            if name != omit_record:
                rows.append([name, digest, str(len(data))])
        if bad_digest:
            rows[0][1] = "sha256=invalid"
        if bad_size:
            rows[0][2] = "0"
        if duplicate_record:
            rows.append(rows[0])
        rows.append([self.record_name, "", ""])
        record = io.StringIO()
        csv.writer(record).writerows(rows)
        files[self.record_name] = record.getvalue().encode()
        if altered_binary:
            files[self.binary_name] = b"wrong solver"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        buffer.seek(0)
        return zipfile.ZipFile(buffer)

    def test_valid_record_and_binary(self):
        with self.archive() as archive:
            builder.check_wheel(archive, self.binary)

    def test_record_corruption_or_missing_member_is_rejected(self):
        for kwargs in (dict(bad_digest=True), dict(bad_size=True), dict(duplicate_record=True),
                       dict(omit_record="gecode_optimize/__init__.py")):
            with self.subTest(kwargs=kwargs), self.archive(**kwargs) as archive, self.assertRaises(ValueError):
                builder.check_wheel(archive, self.binary)

    def test_changed_solver_is_rejected(self):
        with self.archive(altered_binary=True) as archive, self.assertRaisesRegex(ValueError, "changed"):
            builder.check_wheel(archive, self.binary)

    def test_bytecode_is_rejected_even_with_valid_hashes(self):
        for name in ("gecode_optimize/__pycache__/module.pyc", "gecode_optimize/module.pyo"):
            with self.subTest(name=name), self.archive(extra={name: b"code"}) as archive, self.assertRaisesRegex(ValueError, "bytecode"):
                builder.check_wheel(archive, self.binary)

    def test_unsafe_archive_paths_are_rejected(self):
        for name in ("/absolute", "../outside", "gecode_optimize/../../outside"):
            with self.subTest(name=name), self.archive(extra={name: b"x"}) as archive, self.assertRaisesRegex(ValueError, "paths"):
                builder.check_wheel(archive, self.binary)


if __name__ == "__main__":
    unittest.main()
