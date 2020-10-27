import unittest.mock as mock
import unittest
import io
import localbkup as sut
import subprocess
import datetime
import json
import os
import pathlib


class FakeCliArgs():
    def __init__(self, config):
        self.config = config


class ConfigurationTest(unittest.TestCase):

    def test_from_cli_args(self):
        json_file = io.StringIO(json.dumps({
            "files": ["/home/foo/bar", "/home/bar/foo"],
            "password": "foo",
            "destination_folder": "/destination"
        }))
        args = FakeCliArgs(json_file)

        result = sut.Configuration.from_cli_args(args)

        self.assertEqual(result.destination_folder, "/destination")
        self.assertEqual(result.source_files, ["/home/foo/bar", "/home/bar/foo"])
        self.assertEqual(result.password, "foo")

    def test_from_cli_args_with_exclude(self):
        json_file = io.StringIO('{"files": [], "exclude": ["foo", "bar/baz"]}')
        args = FakeCliArgs(json_file)

        result = sut.Configuration.from_cli_args(args)

        self.assertEqual(result.exclude_files, ["foo", "bar/baz"])


class TarCompressor(unittest.TestCase):

    def test_get_tar_cmd(self):
        config = sut.Configuration("/destination", ["/foo"], ["/bar"], "pas")
        result = sut.TarCompressor._get_tar_cmd(config, "/tmpfile")
        self.assertEqual(result, ["tar", "-zcf", "/tmpfile", "--exclude", "/bar", "/foo"])


class MockPopen:

    last_instance = None

    def __init__(self, args, stdin=None, stdout=None):
        self.args = args
        self.communicate_call_count = 0
        self.communicate_args = []
        self.stdin = stdin
        self.stdout = stdout
        MockPopen.last_instance = self

    def communicate(self, arg=None):
        self.communicate_call_count += 1
        self.communicate_args += [arg]

    @property
    def returncode(self):
        return 0


class ShellRunner(unittest.TestCase):

    def test_echo_hello(self):
        with mock.patch.object(subprocess, "Popen", new=MockPopen):
            args = ["echo", "hello"]
            runner = sut.ShellRunner()
            runner(args)
            self.assertEqual(MockPopen.last_instance.args, args)
            self.assertEqual(MockPopen.last_instance.communicate_call_count, 1)

    def test_with_stdin_string(self):
        with mock.patch.object(subprocess, "Popen", new=MockPopen):
            args = ["echo", "hello"]
            runner = sut.ShellRunner()
            runner(args, "foo")
            self.assertEqual(MockPopen.last_instance.args, args)
            self.assertEqual(MockPopen.last_instance.communicate_args, [b"foo"])

    def test_failes_command_not_found(self):
        args = ["I DO NOT EXIST COMMAND ASDJASJKDH"]
        with self.assertRaises(FileNotFoundError):
            runner = sut.ShellRunner()
            runner(args)

    def test_return_code_non_zero(self):
        args = ["bash", "-c", "exit 1"]
        with self.assertRaises(RuntimeError):
            runner = sut.ShellRunner()
            runner(args)


class FileNameGenerator(unittest.TestCase):

    def test_base(self):
        def now_fn(): return datetime.datetime(2020, 10, 12, 4, 5, 6)
        config = sut.Configuration("/destination", [], [], "")
        generator = sut.FileNameGenerator(now_fn)

        result = generator(config, ".tar.gz")

        self.assertEqual(result, "/destination/localbkup_20201012T040506.tar.gz")


class TempFileGeneratorTest(unittest.TestCase):

    def test_make_and_clean_file(self):
        generator = sut.TempFileGenerator()
        file_ = generator.mkfile()
        file_.write(b"FOO")
        self.assertTrue(os.path.exists(file_.name))
        generator.cleanup()
        self.assertFalse(os.path.exists(file_.name))


class ExtractSuffix(unittest.TestCase):

    def test_base(self):
        self.assertEqual(sut.extract_suffix("foo.bar"), ".bar")

    def test_none(self):
        self.assertEqual(sut.extract_suffix("foo"), "")

    def test_many(self):
        self.assertEqual(sut.extract_suffix("foo.bar.baz"), ".bar.baz")
