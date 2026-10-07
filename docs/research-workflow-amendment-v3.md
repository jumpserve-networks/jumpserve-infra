# Implementation amendment v3 — 2026-10-07

Preserve implementation protocol v1 and amendment v2. Add a bounded operator
import for externally executed, documented campaigns. Imports require exact
original files for each run input and available output, record schemas and an
execution revision, dates, producer and limitations. Schema/hash validation does
not establish external execution or scientific validity. Reviews and publications
remain separate steps. Import limits: ten files, 10 MB each, 30 MB aggregate,
10,000 records and 180 seconds of storage work.

Numerical checks reject decimal lexemes that the JSON number parser cannot
preserve, including nonzero underflow, rather than changing them to recorded zero.
Declare a separate decimal-valued adapter for inputs outside this adapter’s number
representation. Decimal subtraction uses precision sufficient for the supplied
finite numbers; absolute comparisons avoid default-context rounding. Add explicit
development regressions for these cases. Preserve all earlier test reports.

Browser validation uses UI readiness rather than network-idle: Next.js production
prefetching can keep requests active after the requested page is ready. Wait for
menu removal and settled theme colors before capturing visual evidence. This is
a verification-method correction, not a scientific finding.
