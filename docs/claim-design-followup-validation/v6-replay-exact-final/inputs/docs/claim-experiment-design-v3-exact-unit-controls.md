# Exact-unit control addendum

Before the final publication replay, replace context-rounded Decimal multiplication
and normalization with exact coefficient/exponent shifts for s/ms/us. Default
Decimal precision could otherwise erase a difference beyond 28 digits or round an
extremely tiny positive quantity to zero. Independent Fraction controls must reject
such mismatches. Bound nonzero decimal exponents to [-1000,1000] so rendering is
bounded; unsupported quantities fail rather than round. Zero remains valid.

Match supported unit symbols with their declared lowercase spelling; spelled-out
unit words may be case-insensitive. Reject a country/other uppercase token such as
US as though it were us. No prompt, schema, runner context or raw model answer is
changed; preserve all preceding replays, make no provider call, and use the same
twenty original v6 answers for the final replay and source-identity gate.
