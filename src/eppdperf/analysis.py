import socket

import deltachat
from deltachat.tracker import ConfigureFailed
import time
import os
import shutil
import imapclient
import smtplib
import ssl
from email.mime.text import MIMEText
from .plugins import SpiderPlugin, TestPlugin, parse_msg
from deltachat.tracker import ConfigureFailed


TESTED_CAPABILITIES = ("IDLE", "CONDSTORE", "QRESYNC", "COMPRESS=DEFLATE", "UIDPLUS", "MOVE")


def grouptest(spac: deltachat.Account, output, accounts: [deltachat.Account], timeout: int):
    """Add all test accounts to a group; all test accounts then write to it; wait until test complete or timeout.

    :param spac: spider account which adds everyone to the group initially
    :param output: Output object which gathers the test results
    :param accounts: test accounts
    :param timeout: timeout in seconds
    """
    # create test group
    begin = time.time()
    print("Creating group " + str(begin))
    group = spac.create_group_chat("Test Group " + str(begin),
                                   contacts=[spac.create_contact(ac.get_config("addr")) for ac in accounts])
    group.send_text("Sender: spider\nBegin: %s" % (str(begin),))

    # The test accounts send messages to the group in the background; see plugins.TestPlugin.ac_incoming_message
    try:
        output.groupmsgs_completed.wait(timeout=timeout)
    except KeyboardInterrupt:
        print("Test interrupted.")

    group_members = []
    for ac in accounts:
        for chat in ac.get_chats():
            if chat.get_name() == group.get_name():
                group_members.append(ac)
    if time.time() > begin + timeout:
        print("Timeout reached.", end=" ")
    if len(group_members) is not len(accounts):
        print("Not added to group: ")
        for ac in accounts:
            if ac not in group_members:
                print(ac.get_self_contact().addr)


def interoptest(output, accounts: [deltachat.Account], timeout: int):
    """send a message from each account to all other accounts.

    :param output: Output object which gathers the test results
    :param accounts: test accounts
    :param timeout: timeout in seconds
    """

    sent_messages = []

    for sender in accounts:
        print("sending messages from %s to %d other accounts" %
              (sender.get_config("addr"), len(accounts) - 1))

        for receiver in accounts:
            if sender == receiver:
                continue
            chat = sender.create_chat(receiver)
            # avoid receiver seeing the sender as a contact request
            receiver.create_chat(sender)
            begin = time.time()
            msg = chat.send_text("Begin: %s\nTest: interop" % (begin,))
            sent_messages.append(msg)

    print("Sent out %s messages, waiting %s seconds" % (len(sent_messages), timeout))
    begin = time.time()
    try:
        while not output.interop_completed.is_set() and time.time() < begin + timeout:
            pending_messages = sent_messages.copy()
            for msg in pending_messages:
                if msg.is_out_failed():
                    receiver = msg.chat.get_name()
                    sender = msg.get_sender_contact().addr
                    status = parse_msg(msg.get_message_info())["error"]
                    output.submit_interop_result(receiver, sender, status)
                    sent_messages.remove(msg)
    except KeyboardInterrupt:
        print("Interrupted Timeout.")


def filetest(spac: deltachat.Account, output, accounts: [deltachat.Account], timeout: int, testfile: str):
    """All test accounts send a test file to the spider.

    :param spac: spider account to which the file is sent
    :param output: Output object which gathers the test results
    :param accounts: test accounts
    :param timeout: timeout in seconds
    :param testfile: absolute path to the test file
    """
    # send file test
    print("Sending %s test file to spider from all accounts:" % (get_file_size(testfile),))
    begin = time.time()
    messages_to_wait = [send_test_file(spac, ac, testfile) for ac in accounts]
    # wait until finished, or timeout
    try:
        while time.time() < begin + timeout:
            if output.filetest_completed.wait(timeout=1):
                break
            messages = []
            for msg in messages_to_wait:
                if msg.is_out_delivered():
                    continue
                elif msg.is_out_failed():
                    addr = msg.account.get_config("addr")
                    reason = parse_msg(msg.get_message_info()).get("error")
                    if reason is None:
                        reason = "unspecified msg.error - see log output"
                    print("%s: sending failed - %s" % (addr, reason))
                    output.submit_filetest_result(addr, reason, [])
                else:
                    messages.append(msg)
            messages_to_wait = messages
    except KeyboardInterrupt:
        print("Test interrupted. File test sending failed for: ")
        for ac in accounts:
            addr = ac.get_config("addr")
            try:
                float(output.sending.get(addr))
            except ValueError:
                print("%s: %s" % (addr, output.sending.get(addr)))
            except TypeError:
                print("%s: timeout" % (addr,))
    if time.time() >= begin + timeout:
        print("Timeout reached. File sending test failed for")
        for ac in accounts:
            if ac.get_self_contact().addr not in output.sending:
                print(ac.get_self_contact().addr)


def recipientstest(spac: deltachat.Account, output, accounts: [deltachat.Account], timeout: int, recipient_nums: [int]):
    """Try to write messages to 5,10,15,25,30,35,40,45,50,55... recipients to find out the limit.

    :param spac: spider account to which the messages are addressed
    :param output: Output object which gathers the test results
    :param accounts: test accounts
    :param timeout: timeout in seconds
    :param maximum: the maximum recipients to try out
    """
    os.system("date")
    print("Recipient Test with %d accounts, steps: %s" % (
          len(accounts), recipient_nums))
    for ac in accounts:
        smtpconn = get_smtpconn(ac)
        for num in recipient_nums:
            try:
                send_smtp_msg(smtpconn, spac, ac, num)
            except smtplib.SMTPDataError as e:
                print("[%s] Sending message to %s recipients failed: %s" % (ac.get_config("addr"), num, str(e)))
                break
            else:
                print("[%s] Sending message to %s recipients success" % (ac.get_config("addr"), num))
                output.submit_recipients_result(ac.get_config("addr"), str(num))


def get_smtpconn(ac: deltachat.Account) -> smtplib.SMTP_SSL:
    """Get a SMTP connection

    :param ac: the test account
    :return: the SMTP connection
    """
    print("Trying to login to %s" % (ac.get_config("addr"),))
    host = ac.get_config("configured_send_server")
    port = int(ac.get_config("configured_send_port"))
    if ac.get_config("configured_send_security") == "1":
        smtpconn = smtplib.SMTP_SSL(host, port)
    elif ac.get_config("configured_send_security") == "2":
        smtpconn = smtplib.SMTP(host, port)
        context = ssl.create_default_context()
        smtpconn.starttls(context=context)
        smtpconn.ehlo()
    else:
        raise ValueError("Failed to connect: can not determine configured_send_security %s for %s" %
                         (ac.get_config("configured_send_security"), ac.get_config("addr")))
    smtpconn.login(ac.get_config("addr"), ac.get_config("mail_pw"))
    return smtpconn


def send_smtp_msg(smtpconn: smtplib.SMTP_SSL, spac: deltachat.Account, ac: deltachat.Account, num: int):
    """Send a test message over an SMTP connection

    :param smtpconn: the SMTP connection which sends the message
    """
    recipients = []
    for i in range(num):
        splitaddr = spac.get_config("addr").partition("@")
        # recipients.append(ac.create_contact("%s+%s@%s" % (splitaddr[0], i, splitaddr[2])))
        recipients.append("%s+%s@%s" % (splitaddr[0], i, splitaddr[2]))
    msg = MIMEText("Trying out to send a message to %s contacts." % (num,))
    msg["Subject"] = "Test Message %s" % (num / 5,)
    msg["To"] = ", ".join(recipients)
    msg["From"] = ac.get_config("addr")
    smtpconn.send_message(msg)


def featurestest(output, accounts: [deltachat.Account]):
    """Find out the IMAP Quota for all test accounts

    :param output: Output object which gathers the test results
    :param accounts: test accounts
    """
    for ac in accounts:
        try:
            imapconn = imapclient.IMAPClient(host=ac.get_config("configured_mail_server"))
        except socket.gaierror:
            print("Could not connect to " + ac.get_config("configured_mail_server"))
            continue
        imapconn.login(ac.get_config("addr"), ac.get_config("mail_pw"))
        results = [x.decode("ascii") for x in imapconn.capabilities()]
        for cond in TESTED_CAPABILITIES:
            output.submit_capability_result(ac.get_config("addr"), cond, cond in results)

        if "QUOTA" in results:
            try:
                quotaint = imapconn.get_quota()[0].limit
            except IndexError:
                output.submit_quota_result(ac.get_config("addr"), "Server Error")
                continue
            if quotaint > 1024 * 1024:
                quota = str(round(quotaint / (1024 * 1024), 3)) + "GB"
            else:
                quota = str(round(quotaint / 1024, 3)) + "MB"
            output.submit_quota_result(ac.get_config("addr"), quota)
        else:
            output.submit_quota_result(ac.get_config("addr"), "Not Supported")


def shutdown_accounts(args, accounts: [deltachat.Account], spac: deltachat.Account):
    """Shut down all DeltaChat accounts and wait until its done.

    :param args: command line arguments
    :param accounts: the test accounts
    :param spac: the spider account
    """
    for ac in accounts:
        ac.shutdown()
    if not args.yes:
        answer = input("Do you want to delete all messages in the %s account? [y/N]" % (spac.get_config("addr"),))
        if answer.lower() == "y":
            for chat in spac.get_chats():
                spac.delete_messages(chat.get_messages())
    else:
        print("deleting all messages in the %s account..." % (spac.get_config("addr"),))
        for chat in spac.get_chats():
            messages = chat.get_messages()
            if messages:
                spac.delete_messages(messages)
    spac.shutdown()
    for ac in accounts:
        ac.wait_shutdown()
    spac.wait_shutdown()


def logintest(spider: dict, credentials: [dict], args, output) -> (deltachat.Account, [deltachat.Account]):
    """Setup spider and test accounts.

    :param spider: an entry dict
    :param credentials: a list of entry dicts
    :param args: the command line arguments
    :param output: output object
    :return: the spider and test accounts
    """
    spac = setup_account(output, spider, args.data_dir, SpiderPlugin,
                         args.debug in spider["addr"], args.timeout, args.quiet)
    accounts = []
    for entry in credentials:
        debug = args.debug in entry["addr"]
        acc = setup_account(output, entry, args.data_dir, TestPlugin, debug, args.timeout, args.quiet)
        accounts.append(acc)
    return spac, accounts


def setup_account(output, entry: dict, data_dir: str, plugin, debug: bool, timeout: int, quiet: bool) -> deltachat.Account:
    """Creates a Delta Chat account for a given credentials dictionary.

    :param output: the Output object which takes care of the results
    :param data_dir: the directory where the accounts the argparse arguments
        passed to this script
    :param entry: a dictionary with at least an "addr" and a "app_pw" key
    :param plugin: a plugin class which the bot will use
    :param debug: True if you want to see logging events for this account
    :param quiet: whether warnings should be printed
    """

    addr = entry["addr"]
    app_pw = entry["app_pw"]

    begin = time.time()

    try:
        os.mkdir(os.path.join(data_dir, addr))
    except FileExistsError:
        pass
    db_path = os.path.join(data_dir, addr, "db.sqlite")

    ac = deltachat.Account(db_path)
    if debug:
        ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
    plug = plugin(ac, output, begin, quiet=quiet)
    ac.add_account_plugin(plug)
    if not ac.is_configured():
        ac.set_config("addr", addr)
    ac.set_config("mail_pw", app_pw)

    for name in ("send_server", "mail_server", "mail_port", "mail_security", "send_port", "send_security"):
        val = entry.get(name)
        if val is not None:
            ac.set_config(name, val)

    ac.set_config("mvbox_move", "0")
    try:
        ac.set_config("mvbox_watch", "0")
    except KeyError:
        pass  # option will be deprecated in deltachat 1.70.1
    ac.set_config("sentbox_watch", "0")
    ac.set_config("bot", "1")
    ac.set_config("mdns_enabled", "0")

    if not ac.is_configured():
        begin = time.time()
        configtracker = ac.configure()
        try:
            configtracker.wait_finish(timeout=timeout)
        except ConfigureFailed as e:
            print("configuration setup failed for %s with password:\n%s" %
                  (ac.get_config("addr"), ac.get_config("mail_pw")))
            raise

        duration = time.time() - begin
        print("%s: %s: successful configuration setup as %s in %.1f seconds." %
              (len(output.accounts)+1, addr, plug.classtype, duration))
        if plugin == TestPlugin:
            output.submit_setup_result(addr, duration)

    # account is configured, let's measure login time
    ac.stop_io()
    plug.imap_connected.clear()
    begin = time.time()
    ac.start_io()
    plug.imap_connected.wait(timeout=timeout)
    duration = time.time() - begin
    if plugin == TestPlugin:
        output.submit_login_result(addr, duration)
        print("%s: successful login as %s in %.1f seconds." %
              (len(output.accounts), addr, duration))

    ac.output = output
    return ac


def send_test_file(spac: deltachat.Account, account: deltachat.Account, testfile: str) -> deltachat.Message:
    """Send the test file to spider.

    :param spac: spider account the file is sent to.
    :param account: test account which sends the file
    :param testfile: absolute path to test file, the default is 15 MB large
    :return the sent message
   """
    chat = account.create_chat(spac)
    # this is a bit early, yes, but with a 15 MB file on my system the delay was only 0.02 seconds.
    begin = str(time.time())
    # need to copy testfile to blobdir to avoid error
    newfilepath = os.path.join(account.get_blobdir(), begin)
    shutil.copy(testfile, newfilepath)
    message = chat.prepare_message_file(newfilepath)
    chat.send_prepared(message)
    return message


def get_file_size(testfile: str) -> str:
    """Return the size of a file

    :param testfile: absolute path to the file
    :return: string with human readable file size
    """
    testfile = os.path.join(os.environ.get("PWD"), testfile)
    testfilebytes = os.path.getsize(testfile)
    if testfilebytes > 1024 * 1024:
        return str(round(testfilebytes / (1024 * 1024))) + "MB"
    else:
        return str(round(testfilebytes / 1024)) + "KB"
