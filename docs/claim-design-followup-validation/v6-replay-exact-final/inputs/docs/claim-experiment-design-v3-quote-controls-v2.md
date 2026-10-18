# Quote-control addendum: signs and compound units

Before the final replay, extend the same deterministic negative controls: a quote
must not cut off a preceding numeric sign/exponent, or truncate a compound unit
such as s^-1 or ms/request into a simple time unit. Otherwise an exact substring
could identify a different quantity. Reject these ambiguous/unsupported forms;
do not guess a sign or compound-unit conversion. Keep preceding replay reports and
the first quote-control protocol unchanged. No model-facing input or provider call
changes. Use the same original twenty answers for the final archived reanalysis.
