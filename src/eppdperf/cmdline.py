#!/usr/bin/env python3

import os
import argparse
import tempfile
from typing import Tuple
from datetime import datetime
from random import getrandbits

from .output import Output
from .analysis import (
    interoptest, grouptest, filetest, recipientstest,
    featurestest, logintest,
    shutdown_accounts, get_file_size
)


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
    parser.add_argument("command", choices=["login", "group", "interop", "file", "recipients", "features"],
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
    parser.add_argument("-v", "--debug", type=str, default="dz0n3zu98q3ud982qufm982uf98u2f0982f",
                        help="show deltachat logs for specific account")
    parser.add_argument("-s", "--select", type=str, default="",
                        help="run the test only for the first address matching the select arg")
    parser.add_argument("-m", "--max_recipients", type=str, default="100,100,5",
                        help="send to specified number of recipients. if comma-sepaerated, it specifies a start number and the second value is a step wise increase")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress deltachat warnings etc.")
    args = parser.parse_args()

    credentials, spider = parse_accounts_file(args.accounts_file)
    if args.command != "interop":
        if args.select == "":
            args.select = "dz0n3zu98q3ud982qufm982uf98u2f0982f"
        for entry in credentials:
            if args.select in entry["addr"]:
                credentials = [entry]
                break

    if args.output is None:
        args.output = "results/%s-%s.csv" % (args.command, datetime.now().strftime("%Y-%m-%d"))
    output = Output(args, len(credentials))

    # ensuring account data directory
    if args.data_dir is None:
        tempdir = tempfile.TemporaryDirectory(prefix="perfanal")
        args.data_dir = tempdir.name
    elif not os.path.exists(args.data_dir):
        os.mkdir(args.data_dir)

    print("Storing account data in %s" % (args.data_dir,))

    spac, accounts = logintest(spider, credentials, args, output)

    if args.command == "group":
        assert spider is not None, "group test needs a spider echobot account to run"
        grouptest(spac, output, accounts, args.timeout)

    elif args.command == "interop":
        interoptest(output, accounts, args.timeout, args.select)

    elif args.command == "file":
        assert spider is not None, "file test needs a spider echobot account to run"
        testfile = generate_file_from_string(args.filesize)
        output.store_file_size(get_file_size(testfile.name))
        filetest(spac, output, accounts, args.timeout, testfile.name)

    elif args.command == "features":
        featurestest(output, accounts)

    elif args.command == "recipients":
        assert spider is not None, "recipients test needs a spider echobot account to run"
        rec = [int(x) for x in args.max_recipients.strip().split(",")]
        if len(rec) == 1:
            recnums = [rec[0]]
        elif len(rec) == 2:
            recnums = list(range(rec[0], 100, rec[1]))
        else:
            raise ValueError("option does not use more than two args")
        try:
            recipientstest(spac, output, accounts, args.timeout, recnums)
        except KeyboardInterrupt:
            print("Test interrupted.")

    shutdown_accounts(args, accounts, spac)
    output.write()


if __name__ == "__main__":
    main()
