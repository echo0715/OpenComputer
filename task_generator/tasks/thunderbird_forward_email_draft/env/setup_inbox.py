#!/usr/bin/env python3
"""Pre-task setup: create an mbox Inbox with a message from legal@company.com."""

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
    """Write an mbox file with the contract review message."""
    local_folders = os.path.join(profile_dir, "Mail", "Local Folders")
    os.makedirs(local_folders, exist_ok=True)

    inbox_path = os.path.join(local_folders, "Inbox")

    date_str = formatdate(time.time(), localtime=True)

    body = (
        "Hi,\n"
        "\n"
        "We have completed the legal review of the proposed vendor contract. "
        "Here are our notes:\n"
        "\n"
        "1. Section 3.2 - Liability clause needs revision\n"
        "2. Section 5.1 - Payment terms are acceptable\n"
        "3. Section 7.4 - Non-compete scope should be narrowed\n"
        "4. Appendix A - Insurance requirements need updating\n"
        "\n"
        "Overall the contract is in good shape with minor revisions needed.\n"
        "\n"
        "Regards,\n"
        "Legal Department"
    )

    mbox_content = (
        f"From legal@company.com {time.strftime('%a %b %d %H:%M:%S %Y')}\n"
        f"From: legal@company.com\n"
        f"To: user@localhost\n"
        f"Subject: Contract Review Notes\n"
        f"Date: {date_str}\n"
        f"Message-ID: <contract-{int(time.time())}@company.com>\n"
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
