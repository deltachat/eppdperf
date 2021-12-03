#!/usr/bin/env python3

import argparse
import os
import tempfile
from typing import Tuple

from .output import Output
from .analysis import perform_measurements


def parse_config_line(line: str):
    """Parse config file line and create an entry out of it.

    :param line: a string with several config options separated by spaces
    :return: a dictionary with account credentials, or None
    """
    if line[0] == "#" or line[0] == "\n":
        return
    entry = { "line" : line }
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-y", "--yes", action="store_true", default=False,
                        help="always answer yes if prompted")
    parser.add_argument("-a", "--accounts_file", help="a file containing mail accounts",
                        default="testaccounts.txt")
    parser.add_argument("-d", "--data_dir", help="directory for the account data",
                        default=None)
    parser.add_argument("-o", "--output", type=str, default="performance.csv",
                        help="output file for the results in CSV format")
    parser.add_argument("-t", "--timeout", type=int, default=90,
                        help="seconds after which tests are aborted")
    parser.add_argument("-f", "--testfile", type=str, default="files/ph4nt_einfache_antworten.mp3",
                        help="path to test file, the default file is 15 MB large")
    args = parser.parse_args()
    output = Output(args.output, args.yes)
    testfile = os.path.join(os.environ.get("PWD"), args.testfile)

    credentials, spider = parse_accounts_file(args.accounts_file)
    assert spider is not None, "tests need a spider echobot account to run"

    # ensuring measurement data directory
    if args.data_dir is None:
        tempdir = tempfile.TemporaryDirectory(prefix="perfanal")
        args.data_dir = tempdir.name
        # rm -r data_dir at the end of the script? ask for removal?
    print("Storing account data in %s" % (args.data_dir,))

    perform_measurements(spider, credentials, output, args, testfile)


if __name__ == "__main__":
    main()
