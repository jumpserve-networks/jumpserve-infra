# Import serialization correction v2

Before database writes, the v1 preparation validation rejected HTTP/2's main
paper retrieved_url: its native field records a supplied-file location rather
than a public HTTP URL. The three v1 candidate files remain preserved; none were
written to Supabase.

The v2 projection uses null for nonpublic URL locations, records which fields
could not be exposed as HTTP URLs, and preserves the exact native field in the
private original database export. Source rows are validated before candidate
files are saved. Scientific labels, native measurements and the declared import
protocol do not change. All corrected candidates use new v2 paths.

During v2 preparation, twelve original IPv6 configuration/epoch summaries had
different DNS and packet missing-day counts. The projection stopped before
saving that candidate. It now groups metrics with identical coverage into
separate summaries, retaining all original statistics and noting that shared
days/metrics are not independent replications. The three successful v2 candidates
remain unchanged, and their exact implementation bytes are retained separately.

The IPv6 projection initially exceeded the frozen 3 MB scientific-row budget.
No candidate or database rows were saved. Its independently stored publication
cells are no longer duplicated inside the protocol wrapper, repeated transfer
text resides on the run, and equal per-metric day coverage is normalized into the
summary columns. All metric values, units and differing missing-day groups are
retained; original full native rows remain in the private hashed export and the
unchanged native tables. No values or scientific records are truncated.
