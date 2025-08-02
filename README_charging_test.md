# OCPP 1.6 Charging Session Test

This directory contains standalone test scripts that simulate an OCPP 1.6 charger connecting to your Home Assistant OCPP integration and performing a complete charging session with energy tracking.

## Files

- `test_charging_session.py` - Complete test script (both phases combined)
- `test_phase1_connect.py` - Phase 1: Connect and register only
- `test_phase2_transaction.py` - Phase 2: Transaction only
- `test_script_validation.py` - Validation script to test components
- `README_charging_test.md` - This documentation file

## Prerequisites

1. **Home Assistant OCPP Integration Running**: Make sure your Home Assistant instance is running with the OCPP integration configured and listening on port 9000.

2. **Python Dependencies**: Install the required packages:

   ```bash
   pip install ocpp websockets
   ```

3. **Configuration**: Ensure your `configuration.yaml` has the OCPP integration configured with the `pulsar` ID tag in the authorization list.

## Usage

### Two-Phase Testing Approach

The testing is now separated into two distinct phases for better control and debugging:

#### Phase 1: Connect and Register

```bash
python test_phase1_connect.py
```

**What it does:**

- Connects to Home Assistant OCPP central system
- Sends boot notification to register the charger
- Sends heartbeat to establish connection
- Sends status notification (available)
- Authorizes the ID tag `pulsar`
- Keeps connection alive for 60 seconds

#### Phase 2: Transaction

```bash
python test_phase2_transaction.py
```

**What it does:**

- Assumes charger is already connected (Phase 1 completed)
- Changes status to preparing → charging
- Starts a transaction with initial meter reading
- Simulates charging with 10 periodic meter value updates
- Stops the transaction with final meter reading
- Reports total energy charged (3.333 kWh)

### Complete Test (Both Phases)

```bash
python test_charging_session.py
```

**What it does:**

- Runs both phases sequentially
- Phase 1: Connect and register
- 5-second pause between phases
- Phase 2: Complete transaction

### Validation

```bash
python test_script_validation.py
```

**What it does:**

- Tests OCPP message creation without connecting
- Validates energy calculations
- Checks configuration values

## Expected Results

After running the tests, you should see in Home Assistant:

1. **In the test output**: Detailed logs of each OCPP message sent/received
2. **In Home Assistant**:
   - A new charger entity `TEST_CHARGER_001`
   - Updated tag energy sensor for `pulsar` showing ~3.333 kWh
   - Session history in the sensor's extra state attributes

## Configuration

You can modify these variables in any of the scripts:

```python
CHARGER_ID = "TEST_CHARGER_001"        # Charger identifier
CENTRAL_SYSTEM_URL = "ws://localhost:9000"  # HA OCPP endpoint
ID_TAG = "pulsar"                      # ID tag to test with
METER_START = 12345                    # Initial meter reading (Wh)
METER_END = 15678                      # Final meter reading (Wh)
```

## Testing Workflow

### Recommended Testing Sequence:

1. **Start Home Assistant** with OCPP integration configured
2. **Run validation** to ensure everything is set up correctly:
   ```bash
   python test_script_validation.py
   ```
3. **Run Phase 1** to connect and register the charger:
   ```bash
   python test_phase1_connect.py
   ```
4. **Check Home Assistant** to see the charger entity appear
5. **Run Phase 2** to perform the charging transaction:
   ```bash
   python test_phase2_transaction.py
   ```
6. **Check Home Assistant** to see the energy sensor update

### Alternative: Complete Test

If you want to run everything in one go:

```bash
python test_charging_session.py
```

## Troubleshooting

**Connection Refused Error**:

- Make sure Home Assistant is running
- Verify OCPP integration is configured and listening on port 9000
- Check that the integration is properly set up in HA

**Authorization Failed**:

- Ensure `pulsar` is in your `authorization_list` in `configuration.yaml`
- Check that the authorization status is set to `Accepted`

**No Energy Tracking**:

- Verify that the tag energy sensors are visible in HA
- Check the HA logs for any sensor-related errors
- Ensure the transaction includes proper meter values with energy data

**Phase 2 Fails**:

- Make sure Phase 1 completed successfully first
- Check that the charger is still connected and registered
- Verify the ID tag authorization is still valid

## Test Scenarios

You can modify the scripts to test different scenarios:

1. **Multiple Sessions**: Run Phase 2 multiple times to test cumulative energy tracking
2. **Different ID Tags**: Change `ID_TAG` to test with other authorized tags
3. **Error Conditions**: Modify the scripts to test authorization failures, connection drops, etc.
4. **Long Sessions**: Increase the number of meter value updates for longer charging sessions
5. **Separate Phases**: Use the two-phase approach to test connection stability and transaction handling independently

## Integration with Existing Tests

This standalone test complements the existing test framework in `tests/` by providing:

- **Real-world simulation** of actual charger behavior
- **End-to-end testing** of the complete energy tracking feature
- **Manual verification** of sensor updates in Home Assistant UI
- **Debugging capability** for troubleshooting integration issues
- **Two-phase testing** for better control and isolation of issues

## Next Steps

After running these tests successfully, you can:

1. **Verify sensor updates** in the Home Assistant UI
2. **Check the logs** for any integration issues
3. **Test with real chargers** using the same OCPP protocol
4. **Extend the test** to cover more complex scenarios
5. **Use the two-phase approach** for debugging specific issues
