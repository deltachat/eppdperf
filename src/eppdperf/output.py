import os
from threading import Event

class Output:
    def __init__(self, outputfile, overwrite, num_accounts):
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

    def submit_login_result(self, addr, duration):
        self.accounts.append(addr)
        self.logins[addr] = duration
        self.groupmsgs[addr] = {}
        if len(self.accounts) == self.num_accounts:
            self.logins_completed.set()

    def submit_1on1_result(self, addr, sendduration, recvduration):
        self.sending[addr] = sendduration
        self.receiving[addr] = recvduration

    def submit_groupadd_result(self, addr, duration):
        self.groupadd[addr] = duration

    def submit_groupmsg_result(self, addr, sender, duration):
        self.groupmsgs[addr][sender] = duration

    def write(self):
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

        #f.write("\naddresses:, ")
        #for addr in self.accounts:
        #    f.write(addr)
        #    f.write(", ")

        f.write("\nfilesending:, ")
        for addr in self.accounts:
            f.write(str(self.sending[addr]))
            f.write(", ")

        f.write("\nreceiving:, ")
        for addr in self.accounts:
            f.write(str(self.receiving[addr]))
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

        # create output file? overwrite?
        # only write the results at the end of the test
        # print test results nicely during test
        #