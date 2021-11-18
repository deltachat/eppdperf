import os

class Output:
    def __init__(self, outputfile, overwrite):
        self.outputfile = outputfile
        self.overwrite = overwrite
        self.accounts = []
        self.logins = {}
        self.sending = {}
        self.receiving = {}
        self.groupadd = {}

    def submit_login_result(self, addr, duration):
        self.accounts.append(addr)
        self.logins[addr] = duration

    def submit_1on1_result(self, addr, sendduration, recvduration):
        self.sending[addr] = sendduration
        self.receiving[addr] = recvduration

    def submit_groupadd_result(self, addr, duration):
        self.groupadd[addr] = duration

    def write(self):
        try:
            f = open(self.outputfile, "x", encoding="utf-8")
        except FileExistsError:
            if input((self.outputfile + " already exists. Do you want to delete it? [Y/n]").lower() != "n") or \
                    self.overwrite is True:
                os.system("rm " + self.outputfile)
                f = open(self.outputfile, "x", encoding="utf-8")
            else:
                exit(0)
        f.write("domains:, ")
        for addr in self.accounts:
            f.write(addr.split("@")[1])
            f.write(", ")

        #f.write("\naddresses:, ")
        #for addr in self.accounts:
        #    f.write(addr)
        #    f.write(", ")

        f.write("\nsending:, ")
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
            f.write(str(self.groupadd[addr]))
            f.write(", ")

        f.close()

        # create output file? overwrite?
        # only write the results at the end of the test
        # print test results nicely during test
        #