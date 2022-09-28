import os
from threading import Event


from .analysis import TESTED_CAPABILITIES


class Output:
    """This class tracks the test results and writes them to file. It also sets events when a test is completed.

    :param args: the command line arguments
    :param num_accounts: how many test account credentials were found in the testaccounts file
    """
    def __init__(self, args, num_accounts: int):
        self.command = args.command
        self.outputfile = args.output
        self.overwrite = args.yes
        self.select = args.select
        self.accounts = []
        self.interop_senders = []
        self.logins = {}
        self.setups = {}
        self.sending = {}
        self.groupadd = {}
        self.groupmsgs = {}
        self.interop = {}
        self.dkimchecks = {}
        self.hops = {}
        self.recipients = {}
        self.quotas = {}
        self.capabilities = {}
        self.num_accounts = num_accounts
        self.groupadd_completed = Event()
        self.filetest_completed = Event()
        self.groupmsgs_completed = Event()
        self.interop_completed = Event()

    def submit_login_result(self, addr: str, duration: float):
        """Submit to output how long the login took. Notifies main thread when all logins are complete.

        :param addr: the email address which successfully logged in
        :param duration: seconds how long the login took
        """
        self.accounts.append(addr)
        self.logins[addr] = duration
        self.groupmsgs[addr] = {}
        self.dkimchecks[addr] = {}

    def submit_setup_result(self, addr: str, duration: float):
        """Submit to output how long the login took. Notifies main thread when all logins are complete.

        :param addr: the email address which successfully logged in
        :param duration: seconds how long the login took
        """
        self.setups[addr] = duration

    def submit_filetest_result(self, addr: str, sendduration: str, hops: list):
        """Submit to output how long the file sending test took. Notifies main thread when all tests are complete.

        :param addr: the email address which successfully sent the file
        :param sendduration: seconds how long the file sending took
        :param hops: the parsed message info, containing hop data
        """
        self.sending[addr] = sendduration
        self.hops[addr] = hops
        if len(self.sending) == len(self.accounts):
            self.filetest_completed.set()

    def submit_recipients_result(self, addr: str, num: str):
        """Submit to output how many recipients this addr succeeded to write to.

        :param addr: the test account which sent out the mails
        :param num: the number of recipients it tried to send to
        """
        self.recipients[addr] = num

    def submit_quota_result(self, addr: str, quota: str):
        """Submit to output how large the quota for a given account is.

        :param addr: the email address with the quota result
        :param quota: whether quota is supported, and how much it is.
        """
        self.quotas[addr] = quota

    def submit_capability_result(self, addr: str, capability: str, supported: bool):
        """Submit to output if imap server supports the capability

        :param addr: the email address with the CONDSTORE result
        :param capability: the capability that is supported
        """
        caps = self.capabilities.setdefault(addr, {})
        caps[capability] = supported

    def submit_groupadd_result(self, addr: str, duration: float):
        """Submit to output how long the group add took. Notifies main thread when all test accounts are in the group.

        :param addr: the email address which was successfully added
        :param duration: seconds how long the group add took
        """
        self.groupadd[addr] = duration
        if len(self.groupadd) == len(self.accounts):
            self.groupadd_completed.set()

    def submit_groupmsg_result(self, addr: str, sender: str, duration: float):
        """Submit to output how long a group message took. Notifies main thread when all test messages arrived.

        :param addr: the email address which received the group message
        :param sender: the email address which sent the group message
        :param duration: seconds how long the message took
        """
        self.groupmsgs[addr][sender] = duration
        for receiver in self.groupmsgs:
            if len(self.groupmsgs[receiver]) != len(self.accounts) - 1:
                return
        self.groupmsgs_completed.set()

    def submit_dkimchecks_result(self, receiver: str, sender: str, content: str):
        """Submit to output the MIME headers of a received message. Notifies the main thread when all test messages arrived.

        :param receiver: the email address which received the test message
        :param sender: the email address which sent the test message
        :param content: the MIME headers of the message
        """
        self.dkimchecks[receiver][sender] = content
        print(content)
        for receiver in self.dkimchecks:
            if len(self.dkimchecks[receiver]) != len(self.accounts) - 1:
                return
        self.interop_completed.set()

    def submit_interop_result(self, receiver: str, sender: str, duration: str):
        """Submit to output how long an interop message took. Alternatively, submit error.

        :param receiver: the email address which received the test message
        :param sender: the email address which sent the test message
        :param duration: how long the message took in seconds; alternatively, the error message.
        """
        d = self.interop.setdefault(receiver, {})
        d[sender] = duration
        try:
            print("%s -> %s: %.2f seconds" % (sender, receiver, float(duration)))
        except ValueError:
            print("[ERROR] %s -> %s\n%s" % (sender, receiver, duration))
            d[sender] = duration.replace(",", " ").replace(";", ".").replace("\n", " ")
        for rec in self.accounts:
            if self.interop.get(rec) is None:
                return  # no results for receiver yet
            if rec not in self.interop_senders and len(self.interop[rec]) < len(self.interop_senders):
                return  # receiver has not gotten message from all senders
            if rec in self.interop_senders and len(self.interop[rec]) < len(self.interop_senders) - 1:
                return  # receiver was also a sender, but hasn't gotten message from all other senders
        self.interop_completed.set()

    def store_file_size(self, filesize: str):
        """Store file size in Output object. Insert file size into output file name

        :param filesize: size of the testfile as human-readable string
        """
        self.filesize = filesize
        parts = self.outputfile[::-1].partition(".")
        self.outputfile = "%s-%s.%s" % (parts[2][::-1], filesize, parts[0][::-1])

    def get_sent_percentage(self, sender: str, results: {dict}) -> float:
        """Return the % of successfully sent messages for a specific sender.

        :param sender: the email address of the sender
        :param results: the results of the group or interop test
        :return: the percentage of successful messages/other test accounts, between 0 and 100.
        """
        success = 0
        for receiver in results:
            result = results[receiver].get(sender)
            try:
                float(result)
                success += 1
            except ValueError:
                continue
            except TypeError:
                continue
        return (success / (len(self.accounts) - 1)) * 100

    def get_received_percentage(self, receiver: str, results: dict) -> float:
        """Return the % of successfully received messages for a specific receiver.

        :param results: the results of the receiver
        :return: the percentage of successful messages/other test accounts, between 0 and 100.
        """
        success = 0
        for result in results:
            try:
                float(results[result])
                success += 1
            except ValueError:
                continue
            except TypeError:
                continue
        if self.command == "interop" and receiver in self.interop_senders:
            return (success / (len(self.interop_senders) - 1)) * 100
        elif self.command == "interop" and receiver not in self.interop_senders:
            return (success / (len(self.interop_senders))) * 100
        else:
            return (success / (len(self.accounts) - 1)) * 100

    def write_directories(self):
        """Write the results to a directory structure. """
        try:
            os.mkdir(self.outputfile)
        except FileExistsError:
            if not self.overwrite:
                answer = input(self.outputfile + " already exists. Do you want to overwrite it? [Y/n] ")
                if answer.lower() == "n":
                    return
            os.system("rm -r " + self.outputfile)
            os.mkdir(self.outputfile)
        print("Writing results to %s" % (self.outputfile,))

        for receiver in self.accounts:
            recfolder = "%s/%s/" % (self.outputfile, receiver)
            os.mkdir(recfolder)
            for sender in self.interop_senders:
                if sender == receiver:
                    pass
                else:
                    try:
                        with open(recfolder + sender, "w+", encoding="utf-8") as f:
                            f.write(self.dkimchecks[receiver][sender])
                    except KeyError:
                        print("timeout for mail from %s to %s" % (sender, receiver))

    def write(self):
        """Write the results to the output file.
        """
        lines = list()

        lines.append(["test accounts (by provider):"])
        if self.command == "interop":
            for addr in self.interop_senders:
                lines[0].append(addr.split("@")[1])
        else:
            for addr in self.accounts:
                lines[0].append(addr.split("@")[1])

        if self.command == "login":
            i = 1
            if len(self.setups) != 0:
                lines.append(["time for first configuration (in seconds):"])
                for addr in self.accounts:
                    try:
                        lines[i].append(self.setups[addr])
                    except KeyError:
                        lines[i].append("already configured")
                i += 1
            lines.append(["time to login (in seconds):"])
            for addr in self.accounts:
                lines[i].append(self.logins[addr])

        if self.command == "features":
            lines.append(["IMAP QUOTA:"])
            for addr in self.accounts:
                lines[1].append(self.quotas[addr])

            for i, cap in enumerate(TESTED_CAPABILITIES):
                lines.append([cap])
                for addr in self.accounts:
                    lines[i+2].append(int(self.capabilities[addr][cap]))

        if self.command == "recipients":
            lines.append(["maximum recipients:"])
            for addr in self.accounts:
                try:
                    lines[1].append(self.recipients[addr])
                except KeyError:
                    lines[1].append("")

        if self.command == "file":
            lines.append(["sent %s file (in seconds):" % (self.filesize,)])
            for addr in self.accounts:
                try:
                    lines[1].append(self.sending[addr])
                except KeyError:
                    lines[1].append("timeout")
            row = 0
            while True:
                onemorerow = False
                lines.append(["hop %s:" % (row + 1,)])
                for addr in self.accounts:
                    try:
                        hop = self.hops[addr][row].replace(",", "").replace(";", "")
                        lines[row + 2].append(hop)
                        onemorerow = True
                    except (KeyError, IndexError):
                        lines[row + 2].append("")
                if not onemorerow:
                    break
                row += 1
            del lines[row + 2]

        if self.command == "group":
            lines.append(["added to group (in seconds):"])
            for addr in self.accounts:
                if addr not in self.groupadd:
                    lines[1].append("timeout")
                    continue
                lines[1].append("%.2f" % (self.groupadd[addr],))

            i = len(lines)
            lines.append(["could send messages to other providers:"])
            for sender in self.accounts:
                lines[i].append(str(self.get_sent_percentage(sender, self.groupmsgs)) + "%")

            i = len(lines)
            lines.append(["received messages from other providers:"])
            for receiver in self.accounts:
                try:
                    lines[i].append(str(self.get_received_percentage(receiver, self.groupmsgs[receiver])) + "%")
                except KeyError:
                    lines[i].append("0%")

            for addr in self.accounts:
                i = len(lines)
                lines.append(["received by %s (in seconds):" % (addr.split("@")[1],)])
                groupresults = self.groupmsgs.get(addr)
                for ac in self.accounts:
                    if addr == ac:
                        lines[i].append("self")
                        continue
                    try:
                        lines[i].append(groupresults[ac])
                    except KeyError:
                        lines[i].append("timeout")

        if self.command == "interop":
            i = 1
            for receiver in self.accounts:
                lines.append(["Received by %s:" % (receiver,)])
                for sender in self.interop_senders:
                    if sender == receiver:
                        lines[i].append("self")
                    else:
                        try:
                            lines[i].append(self.interop[receiver][sender])
                        except KeyError:
                            lines[i].append("timeout")
                i += 1
            lines.append(["could send messages to other providers:"])
            for sender in self.interop_senders:
                lines[i].append(str(self.get_sent_percentage(sender, self.interop)) + "%")
            if len(self.accounts) > len(self.interop_senders):
                lines.append(["test accounts which received messages:"])
                i += 1
                for receiver in self.accounts:
                    lines[i].append(receiver.split("@")[1])
            lines.append(["received messages from other providers:"])
            for receiver in self.accounts:
                try:
                    lines[i+1].append(str(self.get_received_percentage(receiver, self.interop[receiver])) + "%")
                except KeyError:
                    lines[i + 1].append("0%")

        # print output
        for i in range(len(lines)):
            lines[i] = ", ".join(map(str, lines[i]))
        out = "\n".join(lines)
        print("Test results in csv format:")
        print(out)
        # write to .csv output file
        try:
            f = open(self.outputfile, "x", encoding="utf-8")
        except FileExistsError:
            if not self.overwrite:
                answer = input(self.outputfile + " already exists. Do you want to overwrite it? [Y/n] ")
                if answer.lower() == "n":
                    return
            os.system("rm " + self.outputfile)
            f = open(self.outputfile, "x", encoding="utf-8")
        print("Writing results to %s" % (self.outputfile,))
        f.write(out)
        f.close()
