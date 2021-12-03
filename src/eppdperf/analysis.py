
import deltachat
import time
import datetime
import os
import shutil
from .plugins import SpiderPlugin, TestPlugin, parse_msg


def perform_measurements(spider: dict, credentials: list, output, args, testfile: str):
    """ Run several performance tests with the given accounts.

    :param output: Output object which keeps track of the test results and writes them to file.
    :param spider: entry dictionary for the spider account.
    :param args: Namespace object; args as obtained through ArgumentParser.
    :param testfile: the path to the testfile as string.
    :param credentials: a list of entry dictionaries, one per account.
    """
    # setup spider and test accounts
    spac = setup_account(output, spider, args.data_dir, SpiderPlugin)
    accounts = []
    for entry in credentials:
        try:
            accounts.append(setup_account(output, entry, args.data_dir, TestPlugin))
        except AssertionError:
            print("this line doesn't contain valid addr and app_pw: %s" %
                  (entry["line"],))
    output.logins_completed.wait(timeout=args.timeout)

    # create test group
    begin = time.time()
    print("Creating group " + str(begin))
    group = spac.create_group_chat("Test Group " + str(begin),
                                   contacts=[spac.create_contact(entry["addr"]) for entry in credentials])
    group.send_text("Sender: spider\nBegin: %s" % (str(begin),))

    # wait for group messages test, which was initiated by the group creation
    output.groupmsgs_completed.wait(timeout=args.timeout)
    group_members = []
    for ac in accounts:
        for chat in ac.get_chats():
            if chat.get_name() == group.get_name():
                group_members.append(ac)
    if time.time() > begin + args.timeout:
        print("Timeout reached.", end=" ")
    if len(group_members) is not len(accounts):
        print("Not added to group: ")
        for ac in accounts:
            if ac not in group_members:
                print(ac.get_self_contact().addr)

    # send test messages to spider
    testfilebytes = os.path.getsize(testfile)
    if testfilebytes > 1024 * 1024:
        testfilesize = str(round(testfilebytes / (1024 * 1024), 3)) + "MB"
    else:
        testfilesize = str(round(testfilebytes / 1024, 3)) + "KB"
    print("Sending %s test file to spider from all accounts:" % (testfilesize,))
    for ac in accounts:
        if spider is not None:
            if spider["addr"] is not ac.get_self_contact().addr:
                check_account_with_spider(spac, ac, testfile)
                ac.begin = time.time()

    # wait until finished, or timeout
    while len(accounts) > 0:
        for ac in accounts:
            if ac._shutdown_event.is_set():
                accounts.remove(ac)
            elif time.time() > ac.begin + args.timeout:
                print("%d seconds timeout while waiting for echo to %s - test failed." %
                      (args.timeout, ac.get_self_contact().addr))
                output.submit_filetest_result(ac.get_self_contact().addr, "timeout", "timeout")
                ac.shutdown()
                ac.wait_shutdown()
    if not args.yes:
        answer = input("Do you want to delete all messages in the %s account? [y/N]" % (spider["addr"],))
        if answer.lower() == "y":
            for chat in spac.get_chats():
                spac.delete_messages(chat.get_messages())
    else:
        for chat in spac.get_chats():
            spac.delete_messages(chat.get_messages())
    spac.shutdown()
    spac.wait_shutdown()
    output.write()


def setup_account(output, entry: dict, data_dir: str, plugin) -> deltachat.Account:
    """Creates a Delta Chat account for a given credentials dictionary.

    :param output: the Output object which takes care of the results
    :param data_dir: the directory where the accounts the argparse arguments
        passed to this script
    :param entry: a dictionary with at least an "addr" and a "app_pw" key
    :param plugin: a plugin class which the bot will use
    """
    assert entry.get("addr") and entry.get("app_pw")

    begin = time.time()

    os.mkdir(os.path.join(data_dir, entry["addr"]))
    db_path = os.path.join(data_dir, entry["addr"], "db.sqlite")

    ac = deltachat.Account(db_path)
    #ac.add_account_plugin(deltachat.events.FFIEventLogger(ac))
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


def check_account_with_spider(spac: deltachat.Account, account: deltachat.Account, testfile: str):
    """Send a message to spider and check if a reply arrives.

    :param spac: the deltachat.Account object of the spider.
    :param account: a deltachat.Account object to check.
    :param testfile: path to test file, the default is 15 MB large
   """
    chat = account.create_chat(spac)
    # need to copy testfile to blobdir to avoid error
    shutil.copy(testfile, account.get_blobdir())
    newfilepath = os.path.join(account.get_blobdir(), os.path.basename(testfile))
    message = chat.prepare_message_file(newfilepath, mime_type="application/octet-stream")
    chat.send_prepared(message)
