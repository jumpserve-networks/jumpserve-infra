# Local trajectory adapter correction

The first release trajectory driver stopped before any provider invocation:
its local SQL helper captured the database name as a Python default argument at
import, so restoring the global name did not restore that default in a new
process. Retain its failed report and zero provider calls.

Correct the local adapter to use the original frozen database for its default,
and verify `current_database()` before dispatch. The v2 driver reuses the exact
original database, owner, claim/task IDs, inputs, original attempt count and
commitments. No claim attempt, budget or deadline is reset. Runtime, prompt,
scientific criteria and the previously frozen 25-attempt/$30/45-minute release
evaluation bounds are unchanged. Preserve both producer profiles and all errors.
