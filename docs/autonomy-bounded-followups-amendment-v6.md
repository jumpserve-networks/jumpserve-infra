# Completion fixture correction v6

Frozen before the corrected completion calls. The v3 completion campaign made
one successful provider call, then failed its controller-read check because its
producer regenerated a random study namespace after loading the earlier frozen
context. The returned check ID belonged to the frozen context, not that newly
generated fixture. This is a test-producer identity mismatch, not evidence of
a production authorization defect or an incorrect model-selected identifier.
The actual reader rejected the mismatch. Retain every v3 byte and its failure.

Correct only the producer: construct the same controlled partial-run scenario
once, freeze both its complete fixture state and model context before dispatch,
and reconstruct the reader from those exact saved bytes. UUIDs differ from the
original ninth case; do not describe the inputs as identical. Scientific values,
algorithms, source bytes and candidate v8 are unchanged. Verify the complete
fixture/context coverage and control label before calling the provider.

Use the unchanged predeclared decision criteria and two-turn stopping rule in
amendment v5. At most 20 provider calls across all campaigns, at most 1,000 cents
in aggregate conservative reservations, at most two calls/600 seconds in this
corrected campaign. Prior commitments total 848 cents, including the failed
test-producer run; check the remaining 152 cents before each dispatch. Do not
retry uncertain provider calls or change these criteria after seeing answers.
All cases remain exposed development work with primary AI review.
