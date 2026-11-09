"""Fixed source inventory for the owner-selected application/runtime unit target."""
from pathlib import Path

# Operator commands and production qualification harnesses are reported by
# --all-sources. Unknown/new assets remain in the runtime gate by default.
OPERATIONAL_ASSETS = {
    'assets/openclaw/verify-intake-pdf.py',
    'assets/platform/auth-entrypoint-runtime-checks.py',
    'assets/platform/captured-failure-runtime-checks.py',
    'assets/platform/research-runtime-checks.py',
    'assets/platform/install-intake-initialization.py',
    'assets/platform/install-slack-gateway.py',
    'assets/platform/qualify-platform-host.py',
    'assets/platform/qualify-retained-control.py',
    'assets/platform/reconcile-platform-host.py',
}


def source_files(root: Path, include_operations=False):
    patterns = ('agent/**/*.py', 'assets/**/*.py') + (('bin/**/*.py', 'research/**/*.py', 'scripts/**/*.py', 'ami/**/*.py') if include_operations else ())
    return sorted({str(path) for pattern in patterns for path in root.glob(pattern)
        if not any(part in ('package', 'layer', 'tests', 'node_modules', '__pycache__') for part in path.relative_to(root).parts)
        and (include_operations or path.relative_to(root).as_posix() not in OPERATIONAL_ASSETS)})
