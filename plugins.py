import time
import datetime
import deltachat

class ReceivePlugin:
    name = "test account"

    @staticmethod
    @deltachat.account_hookimpl
    def ac_incoming_message(message):
        received = time.time()
        chat = message.create_chat()
        if not chat.can_send():
            # if it's a device message or mailing list, we don't need to look at it.
            return
        sender = message.get_sender_contact().addr
        receiver = message.account.get_self_contact().addr
        if chat.is_group():
            print("%s: joined group chat %s" % (receiver, chat.get_name()))
            return  # for now it's enough to just accept the group chat
        msgcontent = parse_spider_msg(message.text)
        firsttravel = msgcontent.get("testduration")
        secondtravel = received - msgcontent.get("begin")
        print("%s: test message took %.1f seconds to %s and %.1f seconds back." %
              (receiver, firsttravel, sender, secondtravel))
        message.account.output.submit_1on1_result(receiver, firsttravel, secondtravel)
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
