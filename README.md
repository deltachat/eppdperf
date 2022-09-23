# EPPD Provider Perfomance Analysis

This repository measures the performance of different email providers. It is
measured with the `analysis.py` script; the output is tracked in the
[results](https://github.com/deltachat/eppdperf/tree/main/results) folder.

Measurement criteria are:
- How long does account setup take
- How long does the SMTP+IMAP login take
- How long does it take to add an account to a group
- How long does it take to send an attachment
- which long does it take for different mail servers to communicate with each other
- How much storage do servers provide to users
- Do servers support CONDSTORE for synchronizing read state between multi-clients
- Do servers support IDLE for push notifications/instant messaging
- How many recipients does a provider allow
- Does a server add authentication results to the headers

## Qualitative Provider Comparisons

These measurements are part of a broader effort to compare different email
providers for compability with chat-over-email efforts.

For the complete results see [the Delta Chat blog](https://delta.chat/en/2022-01-16-dapsi2blogpost).
You can also view the [results in .ods](https://github.com/deltachat/eppdperf/blob/main/results/e-mail_provider_comparison.ods?raw=true).

![An overview over the provider comparisons.](https://github.com/deltachat/deltachat-pages/raw/master/assets/blog/2022-01-19-eppd-table.png)

## Setup

To run the measurements, you need a `testaccounts.txt` file. You can find an
example at `testaccounts.txt.example`, you just need to fill it with your test
accounts.

```
python3 -m venv venv
. venv/bin/activate
pip install -e .
eppdperf -h
```
