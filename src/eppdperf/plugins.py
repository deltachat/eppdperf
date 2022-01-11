import os.path
import time
import datetime
import deltachat
from deltachat.capi import lib


class Plugin:
    """Parent class for all plugins"""

    def __init__(self, account, output, begin, classtype):
        self.account = account
        self.output = output
        self.begin = begin
        self.classtype = classtype

    @deltachat.account_hookimpl
    def ac_configure_completed(self, success):
        addr = self.account.get_config("addr")
        if success:
            self.account.start_io()
            while lib.dc_get_connectivity(self.account._dc_context) < 3000:
                time.sleep(0.1)
            duration = time.time() - self.begin
            print("%s: %s: successful login as %s in %.1f seconds." %
                  (len(self.output.accounts)+1, addr, self.classtype, duration))
            if self.classtype == "test account":
                self.output.submit_login_result(addr, duration)
        else:
            print("Login failed for %s with password:\n%s" %
                  (self.account.get_config("addr"), self.account.get_config("mail_pw")))
            if self.classtype == "test account":
                self.output.submit_login_result(addr, "login failed")

    @deltachat.account_hookimpl
    def ac_process_ffi_event(self, ffi_event):
        """Log all errors and warnings to STDOUT

        :param ffi_event: deltachat.events.FFIEvent
        """
        logmsg = str(ffi_event)
        if "ERROR" in logmsg or "WARNING" in logmsg:
            if "Ignoring nested protected headers" in logmsg:
                return
            if "rfc724" in logmsg:
                return
            if "inner stream closed" in logmsg:
                return
            if "failed to close folder: NoSession" in logmsg:
                return
            if "failed to fetch all uids: got 0" in logmsg:
                return
            print("[%s] %s" % (self.account.get_config("addr"), logmsg))


class TestPlugin(Plugin):
    """Plugin for the deltachat test accounts.

    :param account: the test account object
    :param output: Output object
    """

    def __init__(self, account: deltachat.Account, output, begin, classtype="test account"):
        super().__init__(account, output, begin, classtype)
        self.group = ""

    @deltachat.account_hookimpl
    def ac_incoming_message(self, message: deltachat.Message):
        received = time.time()

        message.create_chat()
        if not message.chat.can_send():
            # if it's a device message or mailing list, we don't need to look at it.
            return

        # group add test
        if message.chat.is_group():
            # message parsing
            selfaddr = message.account.get_config("addr")
            msgcontent = parse_msg(message.text)
            try:
                duration = received - msgcontent.get("begin")
            except TypeError:
                print("[%s] error: incorrect message: begin is None" % (selfaddr,))
                return
            author = msgcontent.get("sender")
            if author == "spider":
                print("%s: joined group chat %s after %.1f seconds" % (selfaddr, message.chat.get_name(), duration))
                message.chat.send_text("Sender: %s\nBegin: %s" % (selfaddr, str(time.time())))
                self.output.submit_groupadd_result(self.account.get_self_contact().addr, duration)
                self.group = message.chat.get_name()
            else:
                if message.chat.get_name() == self.group:
                    print("%s received message from %s after %.1f seconds" %
                          (selfaddr, author, duration))
                    self.output.submit_groupmsg_result(selfaddr, author, duration)


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
        if message.filename == "":
            return  # only handle filetest

        received = (message.time_received - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()
        # get time_sent from attachment filename - hacky, I know
        sent = float(os.path.basename(message.filename))
        testduration = received - sent
        if sent < self.begin:
            print("spider received outdated file test message from %s after %s seconds." %
                  (message.get_sender_contact().addr, testduration))
            return  # file was sent before test started
        hops = parse_msg(message.get_message_info(), firsthop=message.time_sent)["hops"]
        hops.append(datetime.datetime.strftime(message.time_received, "Received: %Y.%m.%d %H:%M:%S UTC"))
        self.output.submit_filetest_result(message.get_sender_contact().addr, str(testduration), hops)
        print("%s: %s: test message took %.1f seconds to spider." %
              (len(self.output.sending), message.get_sender_contact().addr, testduration))


def parse_msg(text: str, firsthop=None) -> dict:
    """Parse data out of a message.

    :param text: a string containing the message info of a deltachat.message.
    :param firsthop: if you want to get hops, you can pass a msg.sent naive datetime object
    :return: a dictionary with different values parse from the message info.
    """
    lines = text.splitlines()
    response = {"hops": list()}
    if firsthop:
        response["hops"].append(datetime.datetime.strftime(firsthop, "Sent: %Y.%m.%d %H:%M:%S UTC"))
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
        if line.startswith("Error: "):
            response["error"] = line.partition(" ")[2]
        if line.startswith("Hop: "):
            response["hops"].append(line.partition(" ")[2])
    if response.get("received") and response.get("sent"):
        response["tdelta"] = (receiveddt - sentdt).total_seconds()
    return response
