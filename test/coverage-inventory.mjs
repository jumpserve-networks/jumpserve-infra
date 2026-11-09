// Fixed-purpose coverage inventory; no arbitrary commands or source execution.
import {readdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {validateCoverage} from './coverage-policy.mjs';
export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
function walk(directory, extensions) {
  return readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return ['tests', 'node_modules', '__pycache__'].includes(entry.name) ? [] : walk(path, extensions);
    return entry.isFile() && extensions.includes(extname(entry.name)) &&
      !entry.name.endsWith('.d.ts') && !/\.(?:test|spec)\.[cm]?[jt]sx?$/.test(entry.name) ? [path] : [];
  });
}
export function sourceFiles(typescript = false) {
  const files = (typescript ? ['lib', 'lambda', 'bin'] : ['assets']).flatMap(directory => walk(resolve(root, directory), typescript ? ['.ts'] : ['.mjs', '.js']));
  
  return files.sort();
}
export function checkReport(directory = 'coverage/native', expectedFiles = sourceFiles()) {
  const summary = JSON.parse(readFileSync(resolve(root, directory, 'coverage-summary.json'), 'utf8'));
  const result = validateCoverage(summary, expectedFiles);
  writeFileSync(resolve(root, directory, 'gate.json'), JSON.stringify(result, null, 2) + '\n');
  return result;
}

