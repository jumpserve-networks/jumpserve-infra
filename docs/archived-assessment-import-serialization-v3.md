# Main-source crosswalk correction v3

Before database writes, inspection found that the v2 IPv6 projection had 75
sources although its native register has 74. The main-source heuristic did not
recognize IPv6's reference-zero role text and incorrectly inserted the delay
paper fallback. No v2 IPv6 candidate was imported or published.

Main source identity now follows the native reference_number=0, independent of
free-text role/kind labels. Delay alone lacks that original main row and uses
its explicitly retained primary PDF/reading audit. A regression checks that an
unusual reference-zero role cannot select another paper. The v2 candidate and
exact implementation bytes remain retained. Only IPv6 gets a new v3 candidate;
the four correctly sourced v2 candidates are preserved unchanged.
