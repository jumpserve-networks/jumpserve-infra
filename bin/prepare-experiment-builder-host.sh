#!/bin/bash
# Explicit release prerequisite; never invoked by routine local verification.
# Run through the existing audited SSM release path after account verification.
set -euo pipefail
umask 077
test "$(aws sts get-caller-identity --query Account --output text)" = '395567831870'
test "$(id -u)" = '0'
grep -Fxq 'SUPABASE_URL=https://regphejnlvfpyokpniny.supabase.co' /etc/jumpserve-openclaw.env
test -n "${JUMPSERVE_BUILDER_IMAGE:-}"
if [[ ! "$JUMPSERVE_BUILDER_IMAGE" =~ ^[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[a-f0-9]{64}$ ]]; then
  echo 'A reviewed image pinned by immutable repository digest is required.' >&2
  exit 1
fi
dnf install -y docker
systemctl enable --now docker
usermod -aG docker jumpserve
docker pull "$JUMPSERVE_BUILDER_IMAGE"
docker image inspect "$JUMPSERVE_BUILDER_IMAGE" --format '{{.Id}} {{.Os}} {{.Architecture}}'
# The model bridge remains loopback-only and auth stays in its existing store.
# Generated commands receive only the workspace mount, never this env file.
sed -i '/^OPENCLAW_BUILDER_IMAGE=/d;/^RESEARCH_BUILDER_ENABLED=/d' /etc/jumpserve-openclaw.env
printf '%s\n' "OPENCLAW_BUILDER_IMAGE=$JUMPSERVE_BUILDER_IMAGE" 'RESEARCH_BUILDER_ENABLED=true' >> /etc/jumpserve-openclaw.env
chmod 600 /etc/jumpserve-openclaw.env
# Restart/health verification and actual tool/prompt checks belong to the
# explicit release procedure; this script does not activate paper admission.
