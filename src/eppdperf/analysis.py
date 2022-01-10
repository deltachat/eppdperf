import deltachat
import time
import os
import shutil
import imapclient
import smtplib
import ssl
from email.mime.text import MIMEText
from .plugins import SpiderPlugin, TestPlugin


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
    output.groupmsgs_completed.wait(timeout=timeout)

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
    for ac in accounts:
        send_test_file(spac, ac, testfile)
    # wait until finished, or timeout
    output.filetest_completed.wait(timeout=timeout)
    if time.time() >= begin + timeout:
        print("Timeout reached. File sending test failed for")
        for ac in accounts:
            if ac.get_self_contact().addr not in output.sending:
                print(ac.get_self_contact().addr)


def recipientstest(spac: deltachat.Account, output, accounts: [deltachat.Account], timeout: int, maximum: int):
    """Try to write messages to 5,10,15,25,30,35,40,45,50,55... recipients to find out the limit.

    :param spac: spider account to which the messages are addressed
    :param output: Output object which gathers the test results
    :param accounts: test accounts
    :param timeout: timeout in seconds
    :param maximum: the maximum recipients to try out
    """
    trying_accounts = [ac for ac in accounts]
    num = 5
    begin = time.time()
    end = False
    while len(trying_accounts) > 0 and num <= maximum and time.time() < begin + timeout:
        for ac in trying_accounts:
            recipients = []
            for i in range(num):
                splitaddr = spac.get_config("addr").partition("@")
                # recipients.append(ac.create_contact("%s+%s@%s" % (splitaddr[0], i, splitaddr[2])))
                recipients.append("%s+%s@%s" % (splitaddr[0], i, splitaddr[2]))
            # chat = ac.create_group_chat(name=str(num), contacts=recipients)
            # chat.send_text("Trying out to send a message to %s contacts." % (num,))
            if ac.get_config("configured_send_security") == "1":
                smtpconn = smtplib.SMTP_SSL(host=ac.get_config("configured_mail_server"),
                                            port=ac.get_config("configured_send_port"))
            elif ac.get_config("configured_send_security") == "2":
                smtpconn = smtplib.SMTP(host=ac.get_config("configured_mail_server"),
                                        port=ac.get_config("configured_send_port"))
                context = ssl.create_default_context()
                smtpconn.starttls(context=context)
                smtpconn.ehlo()
            else:
                smtpconn = smtplib.SMTP(host=ac.get_config("configured_mail_server"),
                                        port=ac.get_config("configured_send_port"))
            smtpconn.login(ac.get_config("addr"), ac.get_config("mail_pw"))
            msg = MIMEText("Trying out to send a message to %s contacts." % (num,))
            msg["Subject"] = "Test Message %s" % (num/5,)
            msg["To"] = ", ".join(recipients)
            msg["From"] = ac.get_config("addr")
            print("%s sending out message to %s contacts." % (ac.get_config("addr"), num))
            try:
                smtpconn.send_message(msg)
            except smtplib.SMTPDataError as e:
                print("[%s] Sending message to %s recipients failed: %s" % (ac.get_config("addr"), num, str(e)))
                trying_accounts.remove(ac)
                tries = num
                num -= 4
                while num < tries:
                    del recipients[num]
                    msg["To"] = ", ".join(recipients)
                    print("%s sending out message to %s contacts." % (ac.get_config("addr"), num))
                    try:
                        smtpconn.send_message(msg)
                    except smtplib.SMTPDataError as e:
                        print("[%s] Sending message to %s recipients failed: %s" % (ac.get_config("addr"), num, str(e)))
                        break
                    output.submit_recipients_result(ac.get_config("addr"), str(num))
                    num += 1
                num = tries
                continue
            output.submit_recipients_result(ac.get_config("addr"), str(num))
        num += 5
        if end:
            break
        if num > maximum:
            num = maximum
            end = True
    if time.time() > begin + timeout:
        print("Timeout reached.")
    for ac in trying_accounts:
        output.submit_recipients_result(ac.get_config("addr"), "No Limit")


def servercapabilitiestest(output, accounts: [deltachat.Account]):
    """Find out the IMAP Quota for all test accounts

    :param output: Output object which gathers the test results
    :param accounts: test accounts
    """
    for ac in accounts:
        imapconn = imapclient.IMAPClient(host=ac.get_config("configured_mail_server"))
        imapconn.login(ac.get_config("addr"), ac.get_config("mail_pw"))
        results = imapconn.capabilities()
        if b"CONDSTORE" in results:
            output.submit_condstore_result(ac.get_config("addr"))
        if b"QUOTA" in results:
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
            spac.delete_messages(chat.get_messages())
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
    spac = setup_account(output, spider, args.data_dir, SpiderPlugin, args.debug)
    tried_accounts = []
    begin = time.time()
    for entry in credentials:
        try:
            tried_accounts.append(setup_account(output, entry, args.data_dir, TestPlugin, args.debug))
        except AssertionError:
            print("this line doesn't contain valid addr and app_pw: %s" %
                  (entry["line"],))
    output.logins_completed.wait(timeout=args.timeout)
    accounts = []
    if time.time() > begin + args.timeout:
        print("Timeout reached. Not configured:")
    for account in tried_accounts:
        if not account.is_configured():
            print(account.get_config("addr"))
        else:
            accounts.append(account)
    print("Successfully logged in to %s accounts." % (len(accounts),))
    return spac, accounts


def setup_account(output, entry: dict, data_dir: str, plugin, debug: str) -> deltachat.Account:
    """Creates a Delta Chat account for a given credentials dictionary.

    :param output: the Output object which takes care of the results
    :param data_dir: the directory where the accounts the argparse arguments
        passed to this script
    :param entry: a dictionary with at least an "addr" and a "app_pw" key
    :param plugin: a plugin class which the bot will use
    :param debug: email address to debug
    """
    assert entry.get("addr") and entry.get("app_pw")

    begin = time.time()

    try:
        os.mkdir(os.path.join(data_dir, entry["addr"]))
    except FileExistsError:
        pass
    db_path = os.path.join(data_dir, entry["addr"], "db.sqlite")

    ac = deltachat.Account(db_path)
    if entry.get("addr") == debug:
        ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
    ac.add_account_plugin(plugin(ac, output, begin))
    if not ac.is_configured():
        ac.set_config("addr", entry["addr"])
    ac.set_config("mail_pw", entry["app_pw"])

    for name in ("send_server", "mail_server"):
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
    reconfigure = ac.is_configured()
    configtracker = ac.configure(reconfigure=reconfigure)
    if plugin is SpiderPlugin:
        configtracker.wait_finish()
    ac.output = output
    return ac


def send_test_file(spac: deltachat.Account, account: deltachat.Account, testfile: str):
    """Send the test file to spider.

    :param spac: spider account the file is sent to.
    :param account: test account which sends the file
    :param testfile: absolute path to test file, the default is 15 MB large
   """
    chat = account.create_chat(spac)
    # this is a bit early, yes, but with a 15 MB file on my system the delay was only 0.02 seconds.
    begin = str(time.time())
    # need to copy testfile to blobdir to avoid error
    newfilepath = os.path.join(account.get_blobdir(), begin)
    shutil.copy(testfile, newfilepath)
    message = chat.prepare_message_file(newfilepath)
    chat.send_prepared(message)


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
