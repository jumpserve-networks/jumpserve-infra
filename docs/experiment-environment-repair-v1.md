# Experiment environment repair v1

The retained assessment `fe761052-6e57-4d47-a3de-163c6cad905b` exposed two
operational failures on the pinned experiment image: iperf3 3.9 could not obtain
the requested 4,194,304-byte socket buffers, and iproute2 5.15 rejected an explicit
netem seed. Neither is a scientific finding. Original failed observations remain
immutable.

The fixed netem implementation prepares only disposable experiment EC2 hosts.
The trusted bootstrap passes a dedicated-host flag bound to the exact spec hash;
the package runtime forwards it only to the fixed built-in runner. The runner
raises send/receive maxima only when below the frozen request, tests actual
socket allocation in both endpoint namespaces, and checks the kernel's actual
seed readback before traffic. Old tc is replaced only when a seed is required
and its parser lacks support. This builds the `lib tc` targets of upstream
iproute2 6.8.0 and installs only `tc` under `/usr/local/sbin`. Source SHA256:
`03a6cca3d71a908d1f15f7b495be2b8fe851f941458dc4664900d7f45fcf68ce`.
Versions, binary hashes, original commands, host setting changes and readbacks
remain in the hash-bound original observation envelope in Supabase Storage.
Preparation uses the existing per-invocation deadline, shutdown and cancellation
boundaries. No IAM profile is added to an experiment host.

Known command failures become structured operational incidents before assessment.
The existing repair records immediately feed platform blocker triage. The
controller reconciles original model and experiment identities and waits without
new inference while the failing implementation remains installed. A qualified
implementation change resumes planning with new reviews; it does not replay old
jobs or assert that the assessment completed. Earlier valid observations and the
frozen claim/criteria are retained. Legacy failure inspection is hash verified
and explicitly limited to eight original envelopes per collection.

Native builders receive the exact versioned
`research_workflow/skills/network-environment-repair-v1/SKILL.md` as
`network-environment-skill.md`, with its hash in the work packet and delivery
manifest. It describes source diagnostics, trusted dependency provisioning,
kernel qualification and repair escalation. Skill delivery does not grant new
cloud credentials or weaken the existing tool policy.

This change requires a dedicated research runtime/executor qualification; the
generic controller recovery adapter intentionally rejects it. Before a release:

1. Run the unchanged existing research tests and the new environment tests.
   Include the new `experiment_environment.py` and the exact skill file in the
   newly qualified manifest. The staging and CDK validators allow this one skill
   path only when explicitly declared with a matching hash. They do not discover
   or install arbitrary skills.
2. On a disposable Linux EC2 qualification host matching the selected AMI/kernel,
   retain the original failure and then execute both null and explicit seed
   cases with a 4 MiB socket request. Test installation from the old distribution
   tc, source verification, actual socket readbacks, actual qdisc seed readback,
   all five metric identities, receiver byte/time/rate consistency, cleanup and
   the independent deadline. These are exposed operational checks, not paper
   measurements or held-out scientific evidence.
   The fixed credential-free check is
   `python3 -B research_workflow/tests/check_experiment_environment_linux.py --dedicated-experiment-host`.
   It retains the original unprepared case and both prepared cases under
   `/var/lib/jumpserve-environment-qualification`, uses the actual package runtime
   with one shared 900-second deadline, and never writes paper records.
3. Bind the qualified source hashes to a new immutable package executor version
   and research/OpenClaw runtime pins through the dedicated release procedure.
   Do not change scientific criteria, authorization, cost policy or fixed tests.
   Requalify the evaluated runtime with the changed runner contract and skill
   delivery. Existing original jobs retain their old implementation hashes.
4. Verify actual deployed hashes and prepare a new, reviewed acquisition for
   affected claims. Preserve all original failure artifacts and unknown-call
   fences. Claims already in planning/assessment automatically inspect bounded
   batches of settled historical jobs and route the same retained incident
   rather than replaying those jobs.
5. Observe successful new measurements and subsequent controller progress before
   reporting recovery. A shipped fix or resolved operational incident alone is
   not proof of unattended scientific completion.

Local editing does not deploy these changes or alter the current runtime pins.

Primary sources:

- [iperf3 window/socket buffer option](https://github.com/esnet/iperf/blob/master/docs/invoking.rst)
- [iproute2 6.8.0 seed parser and readback](https://github.com/iproute2/iproute2/blob/v6.8.0/tc/q_netem.c)
- [kernel.org release checksum manifest](https://mirrors.edge.kernel.org/pub/linux/utils/net/iproute2/sha256sums.asc)
