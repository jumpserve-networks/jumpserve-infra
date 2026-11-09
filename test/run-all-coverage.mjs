// Fixed local suites only. This command never deploys or invokes live DB tests.
import {mkdirSync, readdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve, relative, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
if (args.some(arg => !['--check', '--all-sources'].includes(arg))) throw new Error('Only --check and --all-sources are supported.');
const includeOperations = args.includes('--all-sources');
const suites = [
  [
    "typescript",
    null,
    [
      "test/run-coverage.mjs",
      "--typescript"
    ],
    "coverage/typescript/gate.json"
  ],
  [
    "python",
    ".venv-unit-tests/bin/python",
    [
      "test/run_unit_coverage.py", ...(includeOperations ? ['--all-sources'] : [])
    ],
    includeOperations ? "coverage/python-all-sources/summary.json" : "coverage/python/summary.json"
  ],
  [
    "native",
    null,
    [
      "test/run-coverage.mjs"
    ],
    "coverage/native/gate.json"
  ]
];
const results = [];
for (const [name, executable, arguments_, path] of suites) {
  const result = spawnSync(executable ? resolve(root, executable) : process.execPath, arguments_, {cwd: root, stdio: 'inherit'});
  let report = null;
  if (result.status === 0) report = JSON.parse(readFileSync(resolve(root, path), 'utf8'));
  results.push({name, passed: result.status === 0, target_met: Boolean(report && (report.complete ?? report.target_met)), report: path});
}
function inventory(directory) {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? ['generated', 'node_modules', '__pycache__'].includes(entry.name) ? [] : inventory(path) : entry.isFile() && ['.sh', '.sql'].includes(extname(entry.name)) ? [relative(root, path)] : [];
  });
}
const unmeasured = includeOperations ? ["ami","assets","bin","database","research","scripts"].flatMap(directory => inventory(resolve(root, directory))).sort() : [];
const summary = {scope: includeOperations ? 'all-maintained-sources' : 'application-runtime', generated_at: new Date().toISOString(), passed: results.every(suite => suite.passed),
  target_met: results.every(suite => suite.passed && suite.target_met) && !unmeasured.length, suites: results, unmeasured};
mkdirSync(resolve(root, 'coverage'), {recursive: true});
writeFileSync(resolve(root, includeOperations ? 'coverage/all-sources-summary.json' : 'coverage/summary.json'), JSON.stringify(summary, null, 2) + '\n');
console.log(JSON.stringify({...summary, unmeasured: undefined, unmeasured_file_count: unmeasured.length}));
process.exitCode = !summary.passed ? 1 : args.includes('--check') && !summary.target_met ? 2 : 0;

