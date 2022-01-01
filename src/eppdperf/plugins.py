import os.path
import time
import datetime
import deltachat


class Plugin:
    """Parent class for all plugins"""

    def __init__(self, account, output, begin, classtype):
        self.account = account
        self.output = output
        self.begin = begin
        self.classtype = classtype

    @deltachat.account_hookimpl
    def ac_configure_completed(self, success):
        if success:
            self.account.start_io()
            duration = time.time() - self.begin
            print("%s: successful login as %s in %.1f seconds." %
                  (self.account.get_self_contact().addr, self.classtype, duration))
            self.output.submit_login_result(self.account.get_self_contact().addr, duration)
        else:
            print("Login failed for %s with password:\n%s" %
                  (self.account.get_config("addr"), self.account.get_config("mail_pw")))

    @deltachat.account_hookimpl
    def ac_process_ffi_event(self, ffi_event):
        """Log all errors and warnings to SDTOUT

        :param ffi_event: deltachat.events.FFIEvent
        """
        logmsg = str(ffi_event)
        if "ERROR" in logmsg or "WARNING" in logmsg:
            if "Ignoring nested protected headers" not in logmsg:
                print("[%s] %s" % (self.account.get_config("addr"), logmsg))


class TestPlugin(Plugin):
    """Plugin for the deltachat test accounts.

    :param account: the test account object
    :param output: Output object
    """

    def __init__(self, account: deltachat.Account, output, begin, classtype="test account"):
        super().__init__(account, output, begin, classtype)

    @deltachat.account_hookimpl
    def ac_incoming_message(self, message: deltachat.Message):
        received = time.time()

        message.create_chat()
        if not message.chat.can_send():
            # if it's a device message or mailing list, we don't need to look at it.
            return

        sender = message.get_sender_contact().addr
        receiver = message.account.get_self_contact().addr

        # message parsing
        msgcontent = parse_msg(message.text)
        filesendduration = msgcontent.get("testduration")
        duration = received - msgcontent.get("begin")
        author = msgcontent.get("sender")

        # group add test
        if message.chat.is_group():
            if author == "spider":
                print("%s: joined group chat %s after %.1f seconds" % (receiver, message.chat.get_name(), duration))
                message.chat.send_text("Sender: %s\nBegin: %s" % (receiver, str(time.time())))
                self.output.submit_groupadd_result(self.account.get_self_contact().addr, duration)
            else:
                print("%s received message from %s after %.1f seconds" %
                      (receiver, author, duration))
                self.output.submit_groupmsg_result(receiver, author, duration)
            return

        # file sending response
        print("%s: test message took %.1f seconds to %s and %.1f seconds back." %
              (receiver, filesendduration, sender, duration))
        self.output.submit_receive_result(receiver, duration)


class SpiderPlugin(Plugin):
    """Plugin for the spider deltachat account.

    :param account: the test account object
    :param output: Output object
    """

    def __init__(self, account: deltachat.Account, output, begin, classtype="spider"):
        super().__init__(account, output, begin, classtype)

    @deltachat.account_hookimpl
    def ac_incoming_message(self, message: deltachat.Message):
        message.create_chat()
        minfo = message.get_message_info()

        if message.is_system_message():
            return  # we don't care about system messages

        if message.chat.is_group():
            return  # can safely ignore group messages. spider only creates it

        # send response to file sending test
        received = (message.time_received - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()
        sent = float(os.path.basename(message.filename))
        testduration = received - sent
        begin = time.time()
        message.chat.send_text("TestDuration: %f\nBegin: %f\n%s" % (testduration, begin, minfo))
        # if the response arrives before timeout, this gets overwritten anyway:
        self.output.submit_filetest_result(message.get_sender_contact().addr, testduration, parse_msg(minfo)["hops"])

    @deltachat.account_hookimpl
    def ac_configure_completed(self, success):
        if success:
            self.account.start_io()
            duration = time.time() - self.begin
            print("%s: successful login as spider in %.1f seconds." %
                  (self.account.get_self_contact().addr, duration))
        else:
            print("Login failed for %s with password:\n%s" %
                  (self.account.get_config("addr"), self.account.get_config("mail_pw")))


def parse_msg(text: str) -> dict:
    """Parse data out of a message.

    :param text: a string containing the message info of a deltachat.message.
    :return: a dictionary with different values parse from the message info.
    """
    lines = text.splitlines()
    response = { "hops": list() }
    for line in lines:
        if line.startswith("TestDuration: "):
            response["testduration"] = float(line.partition(" ")[2])
        if line.startswith("Received: "):
            receivedstr = line.partition(" ")[2]
            receiveddt = datetime.datetime.strptime(receivedstr, "%Y.%m.%d %H:%M:%S")
            response["received"] = (receiveddt - datetime.datetime(1970, 1, 1)).total_seconds()
        if line.startswith("Sent: "):
            sentcontent = line.partition(" ")[2]
            sentstr = sentcontent.partition(" by ")[0]
            sentdt = datetime.datetime.strptime(sentstr, "%Y.%m.%d %H:%M:%S")
            response["sent"] = (sentdt - datetime.datetime(1970, 1, 1)).total_seconds()
        if line.startswith("Begin: "):
            response["begin"] = float(line.partition(" ")[2])
        if line.startswith("Sender: "):
            response["sender"] = line.partition(" ")[2]
        if line.startswith("Hop: "):
            response["hops"].append(line.partition(" ")[2])
    if response.get("received") and response.get("sent"):
        response["tdelta"] = (receiveddt - sentdt).total_seconds()
    return response
