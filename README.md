# EPPD Provider Perfomance Analysis

This repository measures the performance of different email providers. It is
measured with the `analysis.py` script; the output is tracked in the
`performance.csv` file.

Measurement criteria are:
- How long does the SMTP+IMAP login take
- How long does it take to add an account to a group
- How long does it take to send an email
- How long does it take to receive an email
- which long does it take for different mail servers to communicate with each other
- How much storage do servers provide to users
- Do servers support CONDSTORE for synchronizing read state between multi-clients

## Setup

To run this script, you need a `testaccounts.txt` file. You can find an example
at `testaccounts.txt.example`, you just need to fill it with your test
accounts.

```
python3 -m venv venv
. venv/bin/activate
pip install -e .
eppdperf -h
```
