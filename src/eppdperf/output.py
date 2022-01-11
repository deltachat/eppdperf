import os
from threading import Event


class Output:
    """This class tracks the test results and writes them to file. It also sets events when a test is completed.

    :param args: the command line arguments
    :param num_accounts: how many test account credentials were found in the testaccounts file
    """
    def __init__(self, args, num_accounts: int):
        self.command = args.command
        self.outputfile = args.output
        self.overwrite = args.yes
        self.accounts = []
        self.logins = {}
        self.sending = {}
        self.groupadd = {}
        self.groupmsgs = {}
        self.hops = {}
        self.recipients = {}
        self.quotas = {}
        self.condstore = {}
        self.num_accounts = num_accounts
        self.logins_completed = Event()
        self.groupadd_completed = Event()
        self.filetest_completed = Event()
        self.groupmsgs_completed = Event()

    def submit_login_result(self, addr: str, duration: float):
        """Submit to output how long the login took. Notifies main thread when all logins are complete.

        :param addr: the email address which successfully logged in
        :param duration: seconds how long the login took
        """
        self.accounts.append(addr)
        self.logins[addr] = duration
        self.groupmsgs[addr] = {}
        if len(self.accounts) == self.num_accounts:
            self.logins_completed.set()

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

    def submit_condstore_result(self, addr: str):
        """Submit to output if mailserver supports CONDSTORE

        :param addr: the email address with the CONDSTORE result
        """
        self.condstore[addr] = "Supported"

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
        :param sender: the email addres which sent the group message
        :param duration: seconds how long the message took
        """
        self.groupmsgs[addr][sender] = duration
        for receiver in self.groupmsgs:
            if len(self.groupmsgs[receiver]) != len(self.accounts) - 1:
                return
        self.groupmsgs_completed.set()

    def store_file_size(self, filesize: str):
        """Store file size in Output object. Insert file size into output file name

        :param filesize: size of the testfile as human-readable string
        """
        self.filesize = filesize
        parts = self.outputfile[::-1].partition(".")
        self.outputfile = "%s-%s.%s" % (parts[2][::-1], filesize, parts[0][::-1])

    def write(self):
        """Write the results to the output file.
        """
        lines = list()

        lines.append(["test accounts (by provider):"])
        for addr in self.accounts:
            lines[0].append(addr.split("@")[1])

        if self.command == "login":
            lines.append(["time to login (in seconds):"])
            for addr in self.accounts:
                lines[1].append(str(self.logins[addr]))

        if self.command == "server":
            lines.append(["IMAP QUOTA:"])
            lines.append(["CONDSTORE:"])
            for addr in self.accounts:
                lines[1].append(self.quotas[addr])
                try:
                    lines[2].append(self.condstore[addr])
                except KeyError:
                    lines[2].append("Not Supported")

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
                lines[1].append(str(self.groupadd[addr]))

            i = len(lines)
            for addr in self.accounts:
                lines.append(["received by %s (in seconds):" % (addr.split("@")[1],)])
                groupresults = self.groupmsgs.get(addr)
                for ac in self.accounts:
                    if addr == ac:
                        lines[i].append("self")
                        continue
                    try:
                        lines[i].append(str(groupresults[ac]))
                    except KeyError:
                        lines[i].append("timeout")
                i += 1

            lines.append(["received messages from other providers:"])
            for addr in self.accounts:
                percentage = int((len(self.groupmsgs.get(addr)) / (len(self.groupmsgs) - 1) * 100))
                lines[i].append(str(percentage) + "%")

        # print output
        for i in range(len(lines)):
            lines[i] = ", ".join(lines[i])
        out = "\n".join(lines)
        print("Test results in csv format:")
        print(out)

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
