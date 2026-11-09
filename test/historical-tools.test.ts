import {createHash} from 'node:crypto';
import {existsSync, lstatSync, readFileSync} from 'node:fs';
import {basename, resolve, sep} from 'node:path';

const root = resolve(__dirname, '..');
type ArchiveRecord = {original_path: string; archived_path: string; sha256: string; bytes: number};

test('all historical tool and evaluator cohorts retain exact bytes outside supported entrypoints', () => {
  const cohorts = [
    {directory: 'archive/historical-tools', version: 'historical-tools-archive-v1', count: 90, preservePaths: true},
    {directory: 'archive/agent-evaluators/http2', version: 'historical-agent-evaluators-v1', count: 11, preservePaths: false},
    {directory: 'archive/agent-evaluators/ipv6', version: 'historical-agent-evaluators-v1', count: 2, preservePaths: false},
    {directory: 'archive/agent-evaluators/reliable', version: 'historical-agent-evaluators-v1', count: 2, preservePaths: false},
  ];
  const originals = new Set<string>();
  for (const cohort of cohorts) {
    const manifest = JSON.parse(readFileSync(resolve(root, cohort.directory, 'manifest.json'), 'utf8'));
    expect(manifest.version).toBe(cohort.version);
    expect(manifest.source_revision).toMatch(/^[a-f0-9]{40}$/);
    expect(manifest.files).toHaveLength(cohort.count);
    for (const row of manifest.files as ArchiveRecord[]) {
      expect(row.archived_path).toBe(cohort.directory + '/' + (cohort.preservePaths ? row.original_path : basename(row.original_path)));
      expect(originals.has(row.original_path)).toBe(false); originals.add(row.original_path);
      const original = resolve(root, row.original_path), archived = resolve(root, row.archived_path);
      expect(original.startsWith(root + sep)).toBe(true);
      expect(archived.startsWith(resolve(root, cohort.directory) + sep)).toBe(true);
      expect(existsSync(original)).toBe(false);
      expect(lstatSync(archived).isFile()).toBe(true);
      const raw = readFileSync(archived);
      expect(raw.length).toBe(row.bytes);
      expect(createHash('sha256').update(raw).digest('hex')).toBe(row.sha256);
    }
    if (manifest.current_entrypoint) {
      expect(originals.has(manifest.current_entrypoint)).toBe(false);
      expect(lstatSync(resolve(root, manifest.current_entrypoint)).isFile()).toBe(true);
    }
  }
  const tools = JSON.parse(readFileSync(resolve(root, 'maintained-tools.json'), 'utf8'));
  expect(tools.version).toBe('maintained-manual-tools-v1');
  for (const path of tools.manual_programs as string[]) {
    expect(originals.has(path)).toBe(false);
    expect(lstatSync(resolve(root, path)).isFile()).toBe(true);
  }
});
