import os
from threading import Event

class Output:
    """This class tracks the test results and writes them to file. It also sets events when a test is completed.

    :param outputfile: path to a .csv file, where the output is written
    :param overwrite: whether to automatically overwrite the output file
    :param num_accounts: how many test account credentials were found in the testaccounts file
    """
    def __init__(self, outputfile: str, overwrite: bool, num_accounts: int):
        self.outputfile = outputfile
        self.overwrite = overwrite
        self.accounts = []
        self.logins = {}
        self.sending = {}
        self.receiving = {}
        self.groupadd = {}
        self.groupmsgs = {}
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

    def submit_receive_result(self, addr: str, recvduration: float):
        """Submit to output how long the receiving test took. Notifies main thread when all tests are complete.

        :param addr: the email address which successfully sent the file
        :param recvduration: seconds how long the response took. can also be "timeout"
        """
        self.receiving[addr] = recvduration
        if len(self.receiving) == len(self.accounts):
            self.filetest_completed.set()

    def submit_filetest_result(self, addr: str, sendduration: float):
        """Submit to output how long the file sending test took.

        :param addr: the email address which successfully sent the file
        :param sendduration: seconds how long the file sending took
        """
        self.sending[addr] = sendduration

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

    def write(self):
        """Write the results to the ouput file.
        """
        try:
            f = open(self.outputfile, "x", encoding="utf-8")
        except FileExistsError:
            if not self.overwrite:
                answer = input(self.outputfile + " already exists. Do you want to overwrite it? [Y/n] ")
                if answer.lower() == "n":
                    return
            os.system("rm " + self.outputfile)
            f = open(self.outputfile, "x", encoding="utf-8")
        f.write("domains:, ")
        for addr in self.accounts:
            f.write(addr.split("@")[1])
            f.write(", ")

        f.write("\nfilesending:, ")
        for addr in self.accounts:
            try:
                f.write(str(self.sending[addr]))
            except KeyError:
                f.write("timeout")
            f.write(", ")

        f.write("\nreceiving:, ")
        for addr in self.accounts:
            try:
                f.write(str(self.receiving[addr]))
            except KeyError:
                f.write("timeout")
            f.write(", ")

        f.write("\ngroupadd:, ")
        for addr in self.accounts:
            if addr not in self.groupadd:
                f.write("timeout, ")
                continue
            f.write(str(self.groupadd[addr]))
            f.write(", ")

        for addr in self.accounts:
            f.write("\n%s:, " % (addr.split("@")[1],))
            groupresults = self.groupmsgs.get(addr)
            for ac in self.accounts:
                if addr == ac:
                    f.write("self, ")
                    continue
                try:
                    f.write(str(groupresults[ac]))
                except KeyError:
                    f.write("timeout")
                f.write(", ")

        f.close()
