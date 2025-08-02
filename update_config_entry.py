#!/usr/bin/env python3
"""
Script to update the OCPP config entry with charger configuration.
"""

import json
import os

# Path to the config entries file
CONFIG_ENTRIES_FILE = "config/.storage/core.config_entries"


def update_config_entry():
    """Update the OCPP config entry with charger configuration."""

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

    # Add the charger configuration
    charger_config = {
        "TEST_CHARGER_001": {
            "cpid": "charger",
            "max_current": 32,
            "monitored_variables_autoconfig": True,
            "meter_interval": 60,
            "idle_interval": 900,
            "skip_schema_validation": False,
            "force_smart_charging": False,
            "monitored_variables": "Current.Export,Current.Import,Current.Offered,Energy.Active.Export.Interval,Energy.Active.Export.Register,Energy.Active.Import.Interval,Energy.Active.Import.Register,Energy.Reactive.Export.Interval,Energy.Reactive.Export.Register,Energy.Reactive.Import.Interval,Energy.Reactive.Import.Register,Frequency,Power.Active.Export,Power.Active.Import,Power.Factor,Power.Offered,Power.Reactive.Export,Power.Reactive.Import,RPM,SoC,Temperature,Voltage",
        }
    }

    # Update the cpids field
    ocpp_entry["data"]["cpids"] = [charger_config]

    print(f"Updated cpids: {ocpp_entry['data']['cpids']}")

    # Write back to file
    with open(CONFIG_ENTRIES_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print("Config entry updated successfully!")


if __name__ == "__main__":
    update_config_entry()
