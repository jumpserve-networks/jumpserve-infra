# JumpServe skill instruction publishing

The Generator, Verifier, and Coach keep their permissions, validation, and
supporting code in the installed plugin. The authenticated JumpServe connector
reads published workflow Markdown from Supabase. A new connected run selects the
active version for its role, or reads a previously published version by ID when
the owner pins one. Outputs carry the guidance source and SHA-256, with the
version ID for published guidance. Local runs can use the bundled workflow files.

For the first release, apply `202611230003_jumpserve_skill_instructions.sql`,
deploy the connector that recognizes `get_skill_instructions` and the artifact
metadata, then distribute the updated plugin. The migration activates initial
versions matching the three bundled workflow files.

## Publish guidance

Use the Supabase SQL Editor as the database owner. The application service role
can only read published guidance through the getter. Keep keys, private research
inputs, and expanded permissions out of the Markdown. Changes to executable
code, artifact contracts, and authorization use the normal release process.

1. Write the proposed Markdown in a local candidate and review its diff. Exercise
   it in a separate workspace with the installed skill and development inputs.
   For a Generator comparison, use the same pinned Verifier guidance and rubric.
2. Insert the reviewed text as an unpublished version. Edit a draft by inserting
   a new version. Compare the returned SHA-256 with the tested Markdown's digest.
   Dollar quoting preserves the text verbatim, including newlines inside the
   delimiters. Use the `generator`, `verifier`, or `coach` role as appropriate.

   ```sql
   insert into public.research_skill_instruction_versions(role, instructions)
   values ('coach', $workflow$<exact tested Markdown>$workflow$)
   returning version_id, sha256;
   ```

3. Confirm the active version against the baseline you reviewed, then activate
   the exact tested version. If activation reports a stale baseline, review the
   intervening change before retrying.

   ```sql
   select active_version_id from public.research_skill_instruction_settings where role = 'coach';

   select public.research_skill_activate_instructions(
     'coach', '<reviewed-version-id>', '<reviewed-sha256>', '<previous-active-version-id>'
   );
   ```

4. Verify a fresh authenticated `get_skill_instructions` call returns the
   expected ID and checksum. The next invocation picks up the new guidance
   without a deployment. Existing runs retain their pinned guidance.

To roll back, activate the previous published version by its ID and SHA-256
using the current active ID as the expected baseline. The database records each
activation in `research_skill_instruction_publications`. After an uncertain
activation, check the pointer and history before retrying.
