#!/usr/bin/env python3
"""
Script to remove the manually added charger configuration from the OCPP config entry.
"""

import json
import os

# Path to the config entries file
CONFIG_ENTRIES_FILE = "config/.storage/core.config_entries"


def remove_charger_config():
    """Remove the manually added charger configuration from the OCPP config entry."""

    # Read the current config entries
    with open(CONFIG_ENTRIES_FILE, "r") as f:
        data = json.load(f)

    # Find the OCPP config entry
    ocpp_entry = None
    for entry in data["data"]["entries"]:
        if (
            entry["domain"] == "ocpp"
            and entry["entry_id"] == "01K1P2FHDKBEBQMDEHJV1JYDYN"
        ):
            ocpp_entry = entry
            break

    if not ocpp_entry:
        print("OCPP config entry not found!")
        return

    print("Found OCPP config entry:")
    print(f"  Entry ID: {ocpp_entry['entry_id']}")
    print(f"  Current cpids: {ocpp_entry['data'].get('cpids', [])}")

    # Remove the charger configuration (set cpids back to empty list)
    ocpp_entry["data"]["cpids"] = []

    print(f"Updated cpids: {ocpp_entry['data']['cpids']}")

    # Write back to file
    with open(CONFIG_ENTRIES_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print("Charger configuration removed successfully!")


if __name__ == "__main__":
    remove_charger_config()
