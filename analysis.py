#!/usr/bin/env python3

import argparse
import os
import random
import time
from typing import Tuple

# this script assumes you installed deltachat: py.delta.chat/install.html
import deltachat
from plugins import EchoPlugin, ReceivePlugin

class Output:
    def __init__(self, outputfile, overwrite):
        self.outputfile = outputfile
        self.overwrite = overwrite
        self.accounts = []
        self.logins = {}
        self.sending = {}
        self.receiving = {}

    def submit_login_result(self, addr, duration):
        self.accounts.append(addr)
        self.logins[addr] = duration

    def submit_1on1_results(self, addr, sendduration, recvduration):
        self.sending[addr] = sendduration
        self.receiving[addr] = recvduration

    def write(self):
        try:
            f = open(self.outputfile, "x", encoding="utf-8")
        except FileExistsError:
            if input((self.outputfile + " already exists. Do you want to delete it? [Y/n]").lower() != "n") or \
                    self.overwrite is True:
                os.system("rm " + self.outputfile)
                f = open(self.outputfile, "x", encoding="utf-8")
            else:
                exit(0)
        f.write("domains:, ")
        for addr in self.accounts:
            f.write(addr.split("@")[1])
            f.write(", ")

        #f.write("\naddresses:, ")
        #for addr in self.accounts:
        #    f.write(addr)
        #    f.write(", ")

        f.write("\nsending:, ")
        for addr in self.accounts:
            f.write(str(self.sending[addr]))
            f.write(", ")

        f.write("\nreceiving:, ")
        for addr in self.accounts:
            f.write(str(self.receiving[addr]))
            f.write(", ")

        f.close()

        # create output file? overwrite?
        # only write the results at the end of the test
        # print test results nicely during test
        # 


def setup_account(output: object, entry: dict, data_dir: str, plugin: object) -> deltachat.Account:
    """Creates a Delta Chat account for a given credentials dictionary.

    :param output: the Output object which takes care of the results
    :param data_dir: the directory where the accounts the argparse arguments
        passed to this script
    :param entry: a dictionary with at least an "addr" and a "app_pw" key
    :param plugin: a plugin class which the bot will use
    """
    assert entry.get("addr") and entry.get("app_pw")

    begin = time.time()
    # create deltachat.Account
    os.mkdir(os.path.join(data_dir, entry["addr"]))
    db_path = os.path.join(data_dir, entry["addr"], "db.sqlite")

    ac = deltachat.Account(db_path)
    #ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
    ac.add_account_plugin(plugin)
    ac.set_config("addr", entry["addr"])
    ac.set_config("mail_pw", entry["app_pw"])

    for name in ("send_server", "mail_server"):
        val = entry.get(name)
        if val is not None:
            ac.set_config(name, val)

    ac.set_config("mvbox_move", "0")
    ac.set_config("mvbox_watch", "0")
    ac.set_config("sentbox_watch", "0")
    ac.set_config("bot", "1")
    configtracker = ac.configure()
    configtracker.wait_finish()
    ac.start_io()
    duration = time.time() - begin
    print("%s: successful login as %s in %.1f seconds." % (entry["addr"], plugin.name, duration))
    if plugin is not EchoPlugin:
        output.submit_login_result(entry.get("addr"), duration)
    ac.output = output
    return ac


def check_account_with_spider(spac: deltachat.Account, account: deltachat.Account):
    """Send a message to spider and check if a reply arrives.

    :param spac: the deltachat.Account object of the spider.
    :param account: a deltachat.Account object to check.
    """
    chat = account.create_chat(spac)
    chat.send_text("%f" % time.time())


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
                        default="/tmp/" + "".join(random.choices("abcdef",k=5)))
    parser.add_argument("-o", "--output", type=str, default="performance.csv",
                        help="output file for the results in CSV format")
    parser.add_argument("-t", "--timeout", type=int, default=60,
                        help="seconds after which tests are aborted")
    args = parser.parse_args()
    output = Output(args.output, args.yes)

    credentials, spider = parse_accounts_file(args.accounts_file)
    assert spider is not None, "tests need a spider echobot account to run"

    # ensuring measurement data directory
    if not os.path.isdir(args.data_dir):
        print("Storing account data in %s" % (args.data_dir,))
        os.mkdir(args.data_dir)

    # setup spider and test accounts
    spac = setup_account(output, spider, args.data_dir, EchoPlugin)
    accounts = []
    for entry in credentials:
        try:
            accounts.append(setup_account(output, entry, args.data_dir, ReceivePlugin))
        except deltachat.tracker.ConfigureFailed:
            print("Login failed for %s with password:\n%s" %
                    (entry["addr"], entry["app_pw"]))
        except AssertionError:
            print("this line doesn't contain valid addr and app_pw: %s" %
                    (entry["line"],))

    # create test group. who is in it after 60 seconds?
    begin = time.time()
    print("Creating group " + str(begin))
    group = spac.create_group_chat("Test Group " + str(begin),
                                   contacts=[spac.create_contact(entry["addr"]) for entry in credentials])
    group.send_text("Welcome to " + group.get_name())
    group_members = []
    while time.time() < float(begin) + 60:
        if len(accounts) == len(group_members):
            break
        for ac in accounts:
            if ac in group_members:
                continue
            for chat in ac.get_chats():
                if chat.get_name() == group.get_name():
                    group_members.append(ac)
                    print("Added %s after %.1f seconds" % (ac.get_self_contact().addr, time.time() - begin))
    else:
        print("Timeout reached. Not added to group: ", end="")
        for ac in accounts:
            if ac not in group_members:
                print(ac.get_self_contact().addr, end=", ")
        print()

    # send test messages to spider
    for ac in accounts:
        if spider is not None:
            if spider["addr"] is not ac.get_self_contact().addr:
                check_account_with_spider(spac, ac)
                ac.begin = time.time()

    # wait until finished, or timeout
    while len(accounts) > 0:
        for ac in accounts:
            if ac._shutdown_event.is_set():
                accounts.remove(ac)
            elif time.time() > ac.begin + args.timeout:
                print("%.1f seconds timeout while waiting for echo to %s - test failed." %
                        (args.timeout, ac.get_self_contact().addr))
                ac.shutdown()
                ac.wait_shutdown()
    if spider is not None:
        spac.shutdown()
        spac.wait_shutdown()
    output.write()


if __name__ == "__main__":
    main()
