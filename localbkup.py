#!/usr/bin/env python3

import argparse
import os
import json
import subprocess
import logging
import tempfile
import datetime
import shutil
import pathlib

logging.basicConfig(level=logging.INFO)


# Some globals
DEFAULT_CONFIG_FILE_PATH = os.path.expanduser("~/.config/localbkup.json")


# Parser configuration
parser = argparse.ArgumentParser(
    description="Makes a local backup of a list of files into a destination folder."
)
parser.add_argument(
    "-c",
    "--config",
    help=(f"Configuration file. Defaults to {DEFAULT_CONFIG_FILE_PATH}."),
    type=argparse.FileType('r')
)


# Helpers
class Configuration:
    """ Object holding the configuration for the script. """

    def __init__(self, destination_folder, source_files, exclude_files, password):
        """
        @param destination_folder - The destination folder to where the backup should be made.
        @param source_files - A list of all source files.
        @param exclude_files - A list of files to exclude from the bkup.
        @param password - A password used for encryption.
        """
        self.destination_folder = destination_folder
        self.source_files = source_files
        self.exclude_files = exclude_files
        self.password = password

    def __str__(self):
        return f"Configuration(destination_folder={self.destination_folder}, ...)"

    @classmethod
    def from_cli_args(cls, args):
        config_file = args.config
        if config_file is None:
            config_file = open(DEFAULT_CONFIG_FILE_PATH, "r")
        json_config = json.load(config_file)
        config_file.close()
        source_files = json_config.get("files", [])
        exclude_files = json_config.get("exclude", [])
        password = json_config.get("password")
        destination_folder = json_config.get("destination_folder")
        return cls(destination_folder, source_files, exclude_files, password)


class ShellRunner:
    """ Simple runner for shell commands, optionally giving it some stdin. """

    def __call__(self, args, stdin_string=None, stdout=subprocess.PIPE):
        logging.info(f"Running shell command: {args}")
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout)
        if stdin_string is not None:
            process.communicate(stdin_string.encode())
        else:
            process.communicate()
        if process.returncode != 0:
            raise RuntimeError("Shell command has failed :( - check your logs.")


class TarCompressor:
    """ Service used to compress a file using tar. """

    def __init__(self, shellRunner: ShellRunner, tmp_file_generator):
        self.shellRunner = shellRunner
        self.tmp_file_generator = tmp_file_generator

    def __call__(self, config: Configuration):
        """ Compresses all `source_files` from the configuration into a temporary file. """
        tmpfilepath = self.tmp_file_generator.mkfile(suffix=".tar.gz").name
        args = self._get_tar_cmd(config, tmpfilepath)
        self.shellRunner(args)
        return tmpfilepath

    @staticmethod
    def _get_tar_cmd(config, tmpfilepath):
        args = ["tar", "-zcf", tmpfilepath]
        for exclude_file in config.exclude_files:
            args.append("--exclude")
            args.append(exclude_file)
        args += config.source_files
        return args


class Encryptor:
    """ Service responsible for encrypting  """

    def __init__(self, shellRunner, tmp_file_generator):
        self.shellRunner = shellRunner
        self.tmp_file_generator = tmp_file_generator

    def __call__(self, sourcefilepath, config):
        tmpfilesuffix = extract_suffix(sourcefilepath) + ".gpg"
        tmpfile = self.tmp_file_generator.mkfile(suffix=tmpfilesuffix)
        args = ["gpg", "--batch", "--passphrase-fd", "0", "--symmetric", "-o", "-", sourcefilepath]
        self.shellRunner(args, config.password, stdout=tmpfile)
        return tmpfile.name


class FileNameGenerator:
    """ Service responsible for generating file names for the backups """

    def __init__(self, now_fn):
        """
        @param now_fn - A function that returns a `datetime` object for the current datetime.
        """
        self.now_fn = now_fn

    def __call__(self, config, suffix):
        """
        @param config - The configuration file from which the file name is generated.
        """
        file_name = self.now_fn().strftime("localbkup_%Y%m%dT%H%M%S")
        return os.path.join(config.destination_folder, file_name) + suffix


class Runner:
    """ Main runner responsible for doing the backup """

    def __init__(self, compressor, encryptor, file_name_generator):
        self.compressor = compressor
        self.encryptor = encryptor
        self.file_name_generator = file_name_generator

    def __call__(self, config):
        compressed_filepath = self.compressor(config)
        logging.info(f"Compressed to file: {compressed_filepath}")
        encrypted_filepath = self.encryptor(compressed_filepath, config)
        logging.info(f"Encrypted to file: {encrypted_filepath}")
        final_filepath = self.file_name_generator(config, extract_suffix(encrypted_filepath))
        pathlib.Path(final_filepath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(encrypted_filepath, final_filepath)
        logging.info(f"Wrote final file {final_filepath}")


class TempFileGenerator:
    """ A temporary file generation, with utilities for cleaning up as well """

    def __init__(self):
        self.managed_files = []

    def mkfile(self, suffix=None):
        file_ = tempfile.NamedTemporaryFile(suffix=suffix)
        self.managed_files.append(file_)
        return file_

    def cleanup(self):
        """ Cleans up all temporary files created """
        logging.info("Cleaning up...")
        for f in self.managed_files:
            logging.info(f"Removing {f.name}")
            f.close()


def extract_suffix(path):
    filename = path
    out = ""
    while True:
        filename, file_extension = os.path.splitext(filename)
        if not file_extension:
            return out
        out = file_extension + out


# Main function and runner
def main(args):
    config = Configuration.from_cli_args(args)
    shellRunner = ShellRunner()
    tmp_file_generator = TempFileGenerator()
    compressor = TarCompressor(shellRunner, tmp_file_generator)
    encryptor = Encryptor(shellRunner, tmp_file_generator)
    file_name_generator = FileNameGenerator(datetime.datetime.now)
    runner = Runner(compressor, encryptor, file_name_generator)
    try:
        runner(config)
    finally:
        tmp_file_generator.cleanup()


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)
    exit(0)
