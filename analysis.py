#!/usr/bin/env python3

import argparse
import os
import random
import time
import datetime
from typing import Tuple

# this script assumes you installed deltachat: py.delta.chat/install.html
import deltachat

class ReceivePlugin:
    name = "test account"

    @staticmethod
    @deltachat.account_hookimpl
    def ac_incoming_message(message):
        received = time.time()
        message.create_chat()
        if not message.chat.can_send():
            # if it's a device message or mailing list, we don't need to look at it.
            return
        sender = message.get_sender_contact().addr
        receiver = message.account.get_self_contact().addr
        msgcontent = parse_spider_msg(message.text)
        firsttravel = msgcontent.get("testduration")
        secondtravel = received - msgcontent.get("begin")
        print("%s: test message took %.1f seconds to %s and %.1f seconds back." %
              (receiver, firsttravel, sender, secondtravel))
        message.account.output.submit_1on1_results(receiver, firsttravel, secondtravel)
        message.account.shutdown()


class EchoPlugin:
    name = "spider"

    @staticmethod
    @deltachat.account_hookimpl
    def ac_incoming_message(message):
        received = time.time()
        message.create_chat()
        addr = message.get_sender_contact().addr
        if message.is_system_message():
            message.chat.send_text("echoing system message from {}:\n{}".format(addr, message))
        else:
            sent = float(message.text)
            testduration = received - sent
            msginfo = message.get_message_info()
            begin = time.time()
            message.chat.send_text("TestDuration: %f\nBegin: %f\n%s" % (testduration, begin, msginfo))


class Output:
    def __init__(self, outputfile):
        self.outputfile = outputfile
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
        print("domains:", end=" ")
        for addr in self.accounts:
            print(addr.split("@")[1], end=", ")
        print()

        print("addresses:", end=" ")
        for addr in self.accounts:
            print(addr, end=", ")
        print()

        print("sending:", end=" ")
        for addr in self.accounts:
            print(self.sending[addr], end=" ")
        print()

        print("receiving:", end=" ")
        for addr in self.accounts:
            print(self.receiving[addr], end=" ")
        print()

        # create output file? overwrite?
        # only write the results at the end of the test
        # print test results nicely during test
        #

def setup_account(output: object, entry: dict, data_dir: str, plugin: object) -> deltachat.Account:
    """Creates a Delta Chat account for a given credentials dictionary.

    :param output: the Output object which takes care of the results
    :param data_dir: the directory where the accounts the argparse arguments
        passed to this script
    :param entry: a dictionary with at least an "addr" and a "mail_pw" key
    :param plugin: a plugin class which the bot will use
    """
    assert entry.get("addr") and entry.get("mail_pw")

    begin = time.time()
    # create deltachat.Account
    os.mkdir(os.path.join(data_dir, entry["addr"]))
    db_path = os.path.join(data_dir, entry["addr"], "db.sqlite")

    ac = deltachat.Account(db_path)
    #ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
    ac.add_account_plugin(plugin)
    ac.set_config("addr", entry["addr"])
    ac.set_config("mail_pw", entry["mail_pw"])

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
    print("%s: Successful login as %s in %.1f seconds." % (entry["addr"], plugin.name, duration))
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


def parse_spider_msg(info: str) -> dict:
    """Parse data out of a spider response.

    :param info: a string containing the message info of a deltachat.message.
    :return: a dictionary with different values parse from the message info.
    """
    lines = info.splitlines()
    response = {}
    for line in lines:
        if line.startswith("TestDuration: "):
            response["testduration"] = float(line.partition(" ")[2])
        if line.startswith("Received: "):
            receivedstr = line.partition(" ")[2]
            receiveddt = datetime.datetime.strptime(receivedstr, "%Y.%m.%d %H:%M:%S")
            response["received"] = (receiveddt - datetime.datetime(1970,1,1)).total_seconds()
        if line.startswith("Sent: "):
            sentcontent = line.partition(" ")[2]
            sentstr = sentcontent.partition(" by ")[0]
            sentdt = datetime.datetime.strptime(sentstr, "%Y.%m.%d %H:%M:%S")
            response["sent"] = (sentdt - datetime.datetime(1970,1,1)).total_seconds()
        if line.startswith("Begin: "):
            response["begin"] = float(line.partition(" ")[2])
    if response.get("received") and response.get("sent"):
        response["tdelta"] = (receiveddt - sentdt).total_seconds()
    return response


def parse_line(line: str) -> dict:
    """Parse config file line and create an entry out of it.

    :param line: a string with several config options separated by spaces
    :return: a dictionary with account credentials
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
    # import and parse accounts-file
    with open(accounts_file, "r", encoding="UTF-8") as f:
        lines = f.readlines()
    credentials = []
    spider = None
    for line in lines:
        entry = parse_line(line)
        if entry is not None:
            if entry.get("spider") == "true":
                spider = entry
            else:
                credentials.append(entry)
    return credentials, spider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--data_dir", help="directory for the account data",
                        default="/tmp/" + "".join(random.choices("abcdef",k=5)))
    parser.add_argument("-a", "--accounts_file", help="a file containing mail accounts",
                        default="testaccounts.txt")
    parser.add_argument("-t", "--timeout", type=int, default=1500,
                        help="seconds after which tests are aborted")
    parser.add_argument("-o", "--output", type=str, default="results.csv")
    args = parser.parse_args()
    output = Output(args.output)

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
                    (entry["addr"], entry["mail_pw"]))
        except AssertionError:
            print("this line doesn't contain valid addr and mail_pw: %s" %
                    (entry["line"],))

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
