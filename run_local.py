"""
Local-only test runner.

Works around Norton's SSL/TLS scanning on this machine, which breaks both
yfinance (curl_cffi) and ntfy pushes (requests) with certificate errors.
Not needed in GitHub Actions -- only for running monitor.py locally.

Usage:
  python run_local.py             # intraday scan
  python run_local.py --summary   # end-of-day summary
  python run_local.py --test      # send a test push

Set NTFY_TOPIC and (if needed) CA_BUNDLE below or via environment variables.
"""

import os
import runpy

import truststore

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "kv-stock-dips")
CA_BUNDLE = os.environ.get("CA_BUNDLE", r"C:\Users\krish\cacert_with_norton.pem")

os.environ["NTFY_TOPIC"] = NTFY_TOPIC
os.environ["CURL_CA_BUNDLE"] = CA_BUNDLE

# Use the Windows certificate store (trusts Norton's intercepted certs)
# for requests/ntfy, instead of the bundled CA file which curl_cffi needs.
truststore.inject_into_ssl()

runpy.run_path("monitor.py", run_name="__main__")
