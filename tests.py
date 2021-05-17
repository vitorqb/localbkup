import unittest.mock as mock
import unittest
import io
import localbkup as sut
import subprocess
import datetime
import json
import os
import shutil
import tempfile


class LocalBkupTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super(cls)
        sut.setLogger(mock.Mock())


class FakeCliArgs():
    def __init__(self, config):
        self.config = config


class ConfigurationTest(LocalBkupTestCase):

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


class TarCompressor(LocalBkupTestCase):

    def test_get_tar_cmd(self):
        config = sut.Configuration("/destination", ["/foo"], ["/bar"], "pas", 10)
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


class ShellRunner(LocalBkupTestCase):

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

    def test_doesnt_fail_if_check_flag_is_false(self):
        args = ["bash", "-c", "exit 1"]
        runner = sut.ShellRunner(check=False)
        runner(args)

    def test_return_code_non_zero(self):
        args = ["bash", "-c", "exit 1"]
        with self.assertRaises(RuntimeError):
            runner = sut.ShellRunner()
            runner(args)


class FileNameGenerator(LocalBkupTestCase):

    def test_base(self):
        def now_fn(): return datetime.datetime(2020, 10, 12, 4, 5, 6)
        config = sut.Configuration("/destination", [], [], "", None)
        generator = sut.FileNameGenerator(now_fn)

        result = generator(config, ".tar.gz")

        self.assertEqual(result, "/destination/localbkup_20201012T040506.tar.gz")


class TempFileGeneratorTest(LocalBkupTestCase):

    def test_make_and_clean_file(self):
        generator = sut.TempFileGenerator()
        file_ = generator.mkfile()
        file_.write(b"FOO")
        self.assertTrue(os.path.exists(file_.name))
        generator.cleanup()
        self.assertFalse(os.path.exists(file_.name))


class TestOldBackupCleaner(LocalBkupTestCase):

    def setUp(self):
        super().setUp()
        self._tempdir = tempfile.mkdtemp()
        with open(f"{self._tempdir}/localbkup_20201012T040506", "w") as f:
            f.write("one")
        with open(f"{self._tempdir}/localbkup_20201012T040507", "w") as f:
            f.write("two")
        with open(f"{self._tempdir}/localbkup_20201012T040508", "w") as f:
            f.write("three")
        with open(f"{self._tempdir}/not-a-backup", "w") as f:
            f.write("not a backup")

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self._tempdir)

    def test_do_nothing_if_not_enough_files(self):
        cleaner = sut.OldBackupCleaner(self._tempdir, 3)
        cleaner()
        self.assertEqual(
            ["localbkup_20201012T040506",
             "localbkup_20201012T040507",
             "localbkup_20201012T040508",
             "not-a-backup"],
            sorted(os.listdir(self._tempdir))
        )

    def test_removes_one_file(self):
        cleaner = sut.OldBackupCleaner(self._tempdir, 2)
        cleaner()
        self.assertEqual(
            ["localbkup_20201012T040507",
             "localbkup_20201012T040508",
             "not-a-backup"],
            sorted(os.listdir(self._tempdir))
        )

    def test_removes_two_file(self):
        cleaner = sut.OldBackupCleaner(self._tempdir, 1)
        cleaner()
        self.assertEqual(
            ["localbkup_20201012T040508",
             "not-a-backup"],
            sorted(os.listdir(self._tempdir))
        )


class ExtractSuffix(LocalBkupTestCase):

    def test_base(self):
        self.assertEqual(sut.extract_suffix("foo.bar"), ".bar")

    def test_none(self):
        self.assertEqual(sut.extract_suffix("foo"), "")

    def test_many(self):
        self.assertEqual(sut.extract_suffix("foo.bar.baz"), ".bar.baz")
