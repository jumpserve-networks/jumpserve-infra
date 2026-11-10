import {spawnSync} from 'node:child_process';
import {root, checkReport, sourceFiles} from './coverage-inventory.mjs';
const args = process.argv.slice(2);
if (args.some(arg => !['--check', '--typescript'].includes(arg))) throw new Error('Only --check and --typescript are supported.');
const typescript = args.includes('--typescript');
// Cached ts-jest source maps can count emitted compiler helpers as source code.
// Coverage needs a fresh transform; ordinary Jest runs keep their normal cache.
const command = typescript
  ? ['node_modules/jest/bin/jest.js', '--coverage', '--runInBand', '--no-cache', '--coverageThreshold={}']
  : ['node_modules/c8/bin/c8.js', process.execPath, '--test', 'assets/platform/slack-tools/index.test.js', 'test/coverage-policy.test.mjs'];
const result = spawnSync(process.execPath, command, {cwd: root, stdio: 'inherit'});
if (result.status !== 0) process.exitCode = result.status ?? 1;
else {
  const report = checkReport(typescript ? 'coverage/typescript' : 'coverage/native', sourceFiles(typescript));
  console.log(JSON.stringify({inventory_valid: report.valid, target_met: report.complete, files: report.files, missing_files: report.missing, errors: report.errors, totals: report.totals}));
  process.exitCode = !report.valid ? 1 : args.includes('--check') && !report.complete ? 2 : 0;
}
