#!/usr/bin/env python3

import argparse
import tempfile
from typing import Tuple
from datetime import datetime
from random import getrandbits

from .output import Output
from .analysis import grouptest, filetest, recipientstest, servercapabilitiestest, logintest, \
    shutdown_accounts, get_file_size


def parse_config_line(line: str):
    """Parse config file line and create an entry out of it.

    :param line: a string with several config options separated by spaces
    :return: a dictionary with account credentials, or None
    """
    if line[0] == "#" or line[0] == "\n":
        return
    entry = {"line": line}
    parameters = line.rstrip().split(" ")
    for p in parameters:
        argument = p.partition("=")
        if argument[1] == "":
            # no = in parameter
            continue
        entry[argument[0]] = argument[2]
    return entry


def parse_accounts_file(accounts_file: str) -> Tuple[list, dict]:
    """import and parse accounts-file

    :param accounts_file: (str) path to accounts file
    :return: a list with test account entry dicts, a dict with the spider entry dict
    """
    with open(accounts_file, "r", encoding="UTF-8") as f:
        lines = f.readlines()
    credentials = []
    spider = None
    for line in lines:
        entry = parse_config_line(line)
        if entry is not None:
            if entry.get("spider") == "true":
                spider = entry
            else:
                credentials.append(entry)
    return credentials, spider


def generate_file_from_string(filesize: str) -> tempfile.NamedTemporaryFile:
    """Create a file from a string like "20M" or "400K".

    :param filesize: command line argument -f
    :return: a temporary file for testing
    """
    assert filesize[0].isdigit(), "Please specify --filesize in a format like '2M'"
    assert filesize[0].isalnum(), "Please specify --filesize in a format like '2M'"
    kbytes = filesize.lower().partition("k")
    if kbytes[1] == "k":
        return generate_file_from_int(int(kbytes[0]) * 1024)
    mbytes = filesize.lower().partition("m")
    if mbytes[1] == "m":
        return generate_file_from_int(int(mbytes[0]) * 1024 * 1024)
    mbytes = filesize.lower().partition("g")
    if mbytes[1] == "g":
        return generate_file_from_int(int(mbytes[0]) * 1024 * 1024 * 1024)
    return generate_file_from_int(int(filesize))


def generate_file_from_int(filesizeint: int) -> tempfile.NamedTemporaryFile:
    """Create a tempfile with random bytes from a specified size

    :param filesizeint: size of the test file in bytes
    :return: a temporary file for testing
    """
    file = tempfile.NamedTemporaryFile()
    with open(file.name, "wb+") as f:
        f.write(bytearray(getrandbits(8) for _ in range(filesizeint)))
    return file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["login", "group", "file", "recipients", "server"],
                        help="Which test to perform")
    parser.add_argument("-y", "--yes", action="store_true", default=False,
                        help="always answer yes if prompted")
    parser.add_argument("-a", "--accounts_file", help="a file containing mail accounts",
                        default="testaccounts.txt")
    parser.add_argument("-d", "--data_dir", help="directory for the account data",
                        default=None)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="output file for the results in CSV format")
    parser.add_argument("-t", "--timeout", type=int, default=90,
                        help="seconds after which tests are aborted")
    parser.add_argument("-f", "--filesize", type=str, default="2M",
                        help="size of the test file, randomly generated")
    parser.add_argument("-v", "--debug", type=str, default="",
                        help="show deltachat logs for specific account")
    parser.add_argument("-m", "--max_recipients", type=int, default=100,
                        help="the max recipients to test during the recipients test")
    args = parser.parse_args()

    credentials, spider = parse_accounts_file(args.accounts_file)
    if args.output is None:
        args.output = "%s-%s.csv" % (args.command, datetime.now().strftime("%Y-%m-%d"))
    output = Output(args, len(credentials))
    if args.command != "server":
        assert spider is not None, "most tests need a spider echobot account to run"

    # ensuring account data directory
    if args.data_dir is None:
        tempdir = tempfile.TemporaryDirectory(prefix="perfanal")
        args.data_dir = tempdir.name
    print("Storing account data in %s" % (args.data_dir,))

    spac, accounts = logintest(spider, credentials, args, output)

    if args.command == "group":
        grouptest(spac, output, accounts, args.timeout)

    if args.command == "file":
        testfile = generate_file_from_string(args.filesize)
        output.store_file_size(get_file_size(testfile.name))
        filetest(spac, output, accounts, args.timeout, testfile.name)

    if args.command == "server":
        servercapabilitiestest(output, accounts)

    if args.command == "recipients":
        recipientstest(spac, output, accounts, args.timeout, args.max_recipients)

    shutdown_accounts(args, accounts, spac)
    output.write()


if __name__ == "__main__":
    main()
