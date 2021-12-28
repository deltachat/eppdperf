import deltachat
import time
import os
import shutil
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


def setup_test_accounts(spider: dict, credentials: [dict], args, output) -> (deltachat.Account, [deltachat.Account]):
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

    os.mkdir(os.path.join(data_dir, entry["addr"]))
    db_path = os.path.join(data_dir, entry["addr"], "db.sqlite")

    ac = deltachat.Account(db_path)
    if entry.get("addr") == debug:
        ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
    ac.add_account_plugin(plugin(ac, output, begin))
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
        return str(round(testfilebytes / (1024 * 1024), 3)) + "MB"
    else:
        return str(round(testfilebytes / 1024, 3)) + "KB"
