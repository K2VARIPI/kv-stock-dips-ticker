"""Free push notifications via ntfy.sh."""

import os

import requests


def send(title: str, message: str, priority: str = "default",
         tags: str = "chart_with_downwards_trend") -> bool:
    """Send a push. priority: "min", "default", or "high"."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("ERROR: NTFY_TOPIC environment variable not set.")
        return False
    resp = requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": tags,
        },
        timeout=15,
    )
    ok = resp.status_code == 200
    if not ok:
        print(f"ntfy error {resp.status_code}: {resp.text}")
    return ok
