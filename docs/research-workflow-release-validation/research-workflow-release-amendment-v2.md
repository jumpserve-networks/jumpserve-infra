# Production concurrency configuration amendment v2

Recorded 2026-10-07 after the first CloudFormation deployment failed and rolled
back. Original implementation/release protocols and failed attempt remain intact.
AWS reports ConcurrentExecutions=10 and UnreservedConcurrentExecutions=10 for
395567831870/us-east-1. Reserving API 4 plus worker 2 violates the required minimum
unreserved pool of 10. Service Quotas rejected a request for 16 because its default
quota is 1,000, even though this account's applied quota is 10. No support case was
opened and no quota increase was obtained.

Production explicitly sets researchReservedConcurrencyEnabled=false. API and
worker hosting share the existing account pool of 10 concurrent invocations,
including other JumpServe functions. Neither function has a separate reservation
or guarantee of available hosting slots. Shared-pool throttling can delay polls or
API calls. This does not establish fairness, availability or hosting isolation.

The workload limits remain enforced by the original atomic PostgreSQL scheduler:
four running queued jobs globally, two per study, declared exclusive resource
locks, two job slots per invocation, 600-second fenced leases, no automatic
experiment retries. Memory/time/input/observation bounds are unchanged. Direct
interactive numerical checks share hosting capacity and are outside the queued
job slot accounting; no arbitrary submitted code, model or EC2 work is enabled.

Before retrying deployment: pass an additional CDK shared-pool configuration case
and all infrastructure regressions/build; inspect the new diff for unrelated
resource changes. Keep the original reserved-mode cases. Verify deployed function
concurrency configuration and actual scheduled execution. All checks are
development/release regressions; reviewer is the primary AI implementer, not
independent. This amendment changes no scientific results or claim assessments.

Future reserved capacity requires an approved AWS quota and an explicit authorized
configuration release. Do not claim the originally proposed per-function hosting
caps were achieved in this production account.
