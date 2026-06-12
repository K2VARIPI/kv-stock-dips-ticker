"""
Local-only test runner.

Works around Norton's SSL/TLS scanning on this machine, which breaks both
yfinance (curl_cffi) and ntfy pushes (requests) with certificate errors.
Not needed in GitHub Actions -- only for running monitor.py locally.

Usage:
  python run_local.py             # intraday scan
  python run_local.py --summary   # end-of-day summary
  python run_local.py --test      # send a test push

Required environment variables (not hardcoded here -- keep secrets out of git):
  NTFY_TOPIC  your private ntfy.sh topic
  CA_BUNDLE   path to the combined CA bundle (see README for how to build it)
"""

import os
import runpy
import sys

import truststore

if "NTFY_TOPIC" not in os.environ:
    sys.exit("Set NTFY_TOPIC before running (see run_local.py docstring).")
if "CA_BUNDLE" not in os.environ:
    sys.exit("Set CA_BUNDLE before running (see run_local.py docstring).")

os.environ["CURL_CA_BUNDLE"] = os.environ["CA_BUNDLE"]

# Use the Windows certificate store (trusts Norton's intercepted certs)
# for requests/ntfy, instead of the bundled CA file which curl_cffi needs.
truststore.inject_into_ssl()

runpy.run_path("monitor.py", run_name="__main__")
