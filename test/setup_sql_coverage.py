"""Build the pinned SQL profiler inside ignored test artifacts, without system installation."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.test-artifacts/unit-tools'
SOURCE = TOOLS / 'plpgsql-check-2.9'
REVISION = 'a94a858b5f6d823e3533873759d22d1fdac12118'
TAG = 'v2.9.3'
PG_CONFIG = shutil.which('pg_config') or '/opt/homebrew/opt/postgresql@17/bin/pg_config'


def prepare():
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not SOURCE.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', TAG, 'https://github.com/okbob/plpgsql_check.git', str(SOURCE)], check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip()
    if revision != REVISION: raise RuntimeError('SQL profiler source differs from the pinned revision.')
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], cwd=SOURCE, check=True, stdout=subprocess.DEVNULL)
    version = subprocess.check_output([PG_CONFIG, '--version'], text=True).strip()
    if not version.startswith(('PostgreSQL 16.', 'PostgreSQL 17.')): raise RuntimeError('The pinned SQL coverage tool requires PostgreSQL 16 or 17.')
    command = ['make', '-B', '-j2', 'PG_CONFIG=' + PG_CONFIG]
    if platform.system() == 'Darwin':
        sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
        command.append('PG_SYSROOT=' + sdk)
    with (TOOLS / 'sql-profiler-build.log').open('w') as log:
        subprocess.run(command, cwd=SOURCE, check=True, stdout=log, stderr=subprocess.STDOUT)
        # PostgreSQL checks extension catalog membership when reading profiles.
        # Stage a relocatable local installation rather than invent C wrappers
        # or install anything into the developer's PostgreSQL directories.
        stage = TOOLS / 'pgsql-stage'
        install = ['make', 'install', 'PG_CONFIG=' + PG_CONFIG, 'DESTDIR=' + str(stage)]
        if platform.system() == 'Darwin': install.append('PG_SYSROOT=' + sdk)
        subprocess.run(install, cwd=SOURCE, check=True, stdout=log, stderr=subprocess.STDOUT)
    directories = {name: Path(subprocess.check_output([PG_CONFIG, '--' + name], text=True).strip()) for name in ['bindir', 'sharedir', 'pkglibdir']}
    staged = {name: stage / path.relative_to('/') for name, path in directories.items()}
    shutil.copytree(directories['sharedir'], staged['sharedir'], dirs_exist_ok=True)
    staged['bindir'].mkdir(parents=True, exist_ok=True); staged['pkglibdir'].mkdir(parents=True, exist_ok=True)
    for name in ['postgres', 'initdb', 'pg_ctl', 'psql', 'pg_config']: shutil.copy2(directories['bindir'] / name, staged['bindir'] / name)
    suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
    for name in ['plpgsql', 'dict_snowball', 'pgcrypto', 'uuid-ossp']: shutil.copy2(directories['pkglibdir'] / (name + suffix), staged['pkglibdir'] / (name + suffix))
    for name in ['sharedir', 'pkglibdir']:
        actual = Path(subprocess.check_output([str(staged['bindir'] / 'pg_config'), '--' + name], text=True).strip())
        if actual != staged[name]: raise RuntimeError('PostgreSQL is not relocatable within the local test staging directory.')
    library = staged['pkglibdir'] / ('plpgsql_check' + suffix)
    receipt = dict(revision=revision, tag=TAG, postgres=version, pg_config=PG_CONFIG, bindir=str(staged['bindir']), library=str(library), sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    (TOOLS / 'sql-profiler.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__': print(json.dumps(prepare()))
