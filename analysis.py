#!/usr/bin/env python3

import argparse
import os
import shutil
import random
import time
import datetime
from typing import Tuple

# this script assumes you installed deltachat: py.delta.chat/install.html
import deltachat
from plugins import EchoPlugin, ReceivePlugin, parse_msg
from output import Output


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


def check_account_with_spider(spac: deltachat.Account, account: deltachat.Account, testfile: os.PathLike, timeout: int):
    """Send a message to spider and check if a reply arrives.

    :param spac: the deltachat.Account object of the spider.
    :param account: a deltachat.Account object to check.
    :param testfile: path to test file, the default is 15 MB large
    :param timeout: seconds until the script gives up
   """
    chat = account.create_chat(spac)
    # need to copy testfile to blobdir to avoid error
    shutil.copy(testfile, account.get_blobdir())
    newfilepath = os.path.join(account.get_blobdir(), os.path.basename(testfile))
    message = chat.prepare_message_file(newfilepath, mime_type="application/octet-stream")
    chat.send_prepared(message)
    begin = time.time()
    while message.is_out_delivered() is False and time.time() < begin + timeout:
        time.sleep(0.5)
    else:
        # currently throws warning: The message Mr.X@testrun.org has no UID on the server to delete
        account.delete_messages([message])


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
    parser.add_argument("-t", "--timeout", type=int, default=90,
                        help="seconds after which tests are aborted")
    parser.add_argument("-f", "--testfile", type=str, default="ph4nt_einfache_antworten.mp3",
                        help="path to test file, the default file 15 MB large")
    args = parser.parse_args()
    output = Output(args.output, args.yes)
    testfile = os.path.join(os.environ.get("PWD"), args.testfile)

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
    group.send_text("Sender: spider\nBegin: %s" % (str(begin),))
    group_members = []
    while time.time() < float(begin) + args.timeout:
        if len(accounts) == len(group_members):
            break
        for ac in accounts:
            if ac in group_members:
                continue
            for chat in ac.get_chats():
                if chat.get_name() == group.get_name():
                    group_members.append(ac)
                    output.submit_groupadd_result(ac.get_self_contact().addr, time.time() - begin)
    else:
        print("Timeout reached. Not added to group: ", end="")
        for ac in accounts:
            if ac not in group_members:
                print(ac.get_self_contact().addr, end=", ")
        print()

    begin = time.time()
    counter = []
    for ac in group_members:
        counter.append(ac)
    while time.time() < float(begin) + args.timeout and len(counter) > 0:
        for ac in counter:
            for chat in ac.get_chats():
                if chat.get_name() == group.get_name():
                    grp = chat
            msgs = grp.get_messages()
            for msg in msgs:
                if msg.is_in_seen():
                    continue
                msg.mark_seen()
                msgcontent = parse_msg(msg.text)
                if msg.time_received is None or msgcontent.get("sender") == "spider":
                    continue
                msgreceived = (msg.time_received - datetime.datetime(1970, 1, 1)).total_seconds()
                duration = msgreceived - msgcontent.get("begin")
                print("%s received message from %s after %.1f seconds" % (ac.get_self_contact().addr, msgcontent["sender"], duration))
                output.submit_groupmsg_result(ac.get_self_contact().addr, msgcontent["sender"], duration)
                if len(output.groupmsgs.get(ac.get_self_contact().addr)) == len(group_members) - 1:
                    counter.remove(ac)

    # send test messages to spider
    for ac in accounts:
        if spider is not None:
            if spider["addr"] is not ac.get_self_contact().addr:
                check_account_with_spider(spac, ac, testfile, args.timeout)
                ac.begin = time.time()

    # wait until finished, or timeout
    while len(accounts) > 0:
        for ac in accounts:
            if ac._shutdown_event.is_set():
                accounts.remove(ac)
            elif time.time() > ac.begin + args.timeout:
                print("%d seconds timeout while waiting for echo to %s - test failed." %
                      (args.timeout, ac.get_self_contact().addr))
                output.submit_1on1_result(ac.get_self_contact().addr, "timeout", "timeout")
                ac.shutdown()
                ac.wait_shutdown()
    if not args.yes:
        answer = input("Do you want to delete all messages in the %s account? [y/N]" % (spider["addr"],))
        if answer.lower() == "y":
            spac.delete_messages(spac.get_chats())
        spac.shutdown()
        spac.wait_shutdown()
    output.write()


if __name__ == "__main__":
    main()
