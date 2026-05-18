#!/usr/bin/env python3
"""Pre-task setup: create an mbox Inbox with a message from supplier@parts.com."""

import glob
import os
import time
from email.utils import formatdate


def find_thunderbird_profile():
    """Find the default Thunderbird profile directory."""
    candidates = glob.glob(os.path.expanduser("~/.thunderbird/*.default*"))
    if not candidates:
        raise FileNotFoundError("No Thunderbird profile found matching ~/.thunderbird/*.default*")
    return candidates[0]


def create_inbox(profile_dir):
    """Write an mbox file with the supplier quote message."""
    local_folders = os.path.join(profile_dir, "Mail", "Local Folders")
    os.makedirs(local_folders, exist_ok=True)

    inbox_path = os.path.join(local_folders, "Inbox")

    date_str = formatdate(time.time(), localtime=True)

    body = (
        "Dear Customer,\n"
        "\n"
        "Thank you for your inquiry. We are pleased to provide the following quote:\n"
        "\n"
        "- Part BX-2200: $45.00 per unit\n"
        "- Part BX-3100: $72.00 per unit\n"
        "- Part CX-1000: $28.00 per unit\n"
        "\n"
        "Quantity discounts available for orders over 100 units.\n"
        "\n"
        "Best regards,\n"
        "Sales Team\n"
        "Parts Supplier Co."
    )

    mbox_content = (
        f"From supplier@parts.com {time.strftime('%a %b %d %H:%M:%S %Y')}\n"
        f"From: supplier@parts.com\n"
        f"To: user@localhost\n"
        f"Subject: Quote for Components\n"
        f"Date: {date_str}\n"
        f"Message-ID: <quote-{int(time.time())}@parts.com>\n"
        f"MIME-Version: 1.0\n"
        f"Content-Type: text/plain; charset=UTF-8\n"
        f"\n"
        f"{body}\n"
        f"\n"
    )

    with open(inbox_path, "w") as f:
        f.write(mbox_content)

    print(f"Inbox created at {inbox_path}")


if __name__ == "__main__":
    profile = find_thunderbird_profile()
    create_inbox(profile)
