#!/usr/bin/env python3
"""Pre-task setup: create an existing contact (David Lee) in Thunderbird's address book."""

import glob
import os
import sqlite3
import uuid


def find_thunderbird_profile():
    """Find the default Thunderbird profile directory."""
    candidates = glob.glob(os.path.expanduser("~/.thunderbird/*.default*"))
    if not candidates:
        raise FileNotFoundError("No Thunderbird profile found matching ~/.thunderbird/*.default*")
    return candidates[0]


def setup_abook(profile_dir):
    """Create/open abook.sqlite and insert the David Lee contact."""
    abook_path = os.path.join(profile_dir, "abook.sqlite")
    conn = sqlite3.connect(abook_path)
    cur = conn.cursor()

    # Create tables if they don't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            card TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lists (
            uid TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            nickName TEXT,
            description TEXT
        )
    """)
    conn.commit()

    # Generate a unique card UID
    card_uid = str(uuid.uuid4())

    # Insert contact properties
    properties = [
        (card_uid, "DisplayName", "David Lee"),
        (card_uid, "FirstName", "David"),
        (card_uid, "LastName", "Lee"),
        (card_uid, "PrimaryEmail", "david@oldcompany.com"),
        (card_uid, "Company", "OldCompany Inc"),
    ]
    cur.executemany("INSERT INTO properties (card, name, value) VALUES (?, ?, ?)", properties)
    conn.commit()
    conn.close()
    print(f"Contact 'David Lee' created in {abook_path}")


if __name__ == "__main__":
    profile = find_thunderbird_profile()
    setup_abook(profile)
