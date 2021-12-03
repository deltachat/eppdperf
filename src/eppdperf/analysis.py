
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
                origin = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
                msgreceived = (msg.time_received - origin).total_seconds()
                duration = msgreceived - msgcontent.get("begin")
                print("%s received message from %s after %.1f seconds" %
                      (ac.get_self_contact().addr, msgcontent["sender"], duration))
                output.submit_groupmsg_result(ac.get_self_contact().addr, msgcontent["sender"], duration)
                if len(output.groupmsgs.get(ac.get_self_contact().addr)) == len(group_members) - 1:
                    counter.remove(ac)

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
                output.submit_1on1_result(ac.get_self_contact().addr, "timeout", "timeout")
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
    ac.add_account_plugin(plugin())
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
    if plugin is not SpiderPlugin:
        output.submit_login_result(entry.get("addr"), duration)
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

