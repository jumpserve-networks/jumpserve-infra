"""Run local Python unit tests and inventory every application/runtime source."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from runtime_inventory import source_files
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--all-sources',action='store_true',help='Also report operator release, AMI, campaign and maintenance scripts.');args=parser.parse_args()
 import coverage
 directory=ROOT/'coverage'/('python-all-sources' if args.all_sources else 'python');directory.mkdir(parents=True,exist_ok=True)
 config=ROOT/'.coveragerc';env=dict(os.environ,UNIT_COVERAGE_ROOT=str(ROOT),COVERAGE_FILE=str(directory/'.coverage'))
 subprocess.run([sys.executable,'-m','coverage','erase','--rcfile',str(config)],cwd=ROOT,env=env,check=True)
 started=time.monotonic();result=subprocess.run([sys.executable,'-m','coverage','run','--rcfile',str(config),'-m','unittest','discover','-s','test','-p','*_test.py'],cwd=ROOT,env=env,capture_output=True,text=True)
 (directory/'unit-tests.log').write_text(result.stdout+result.stderr)
 if result.returncode:print((result.stdout+result.stderr)[-10000:],flush=True)
 os.environ.update(UNIT_COVERAGE_ROOT=str(ROOT),COVERAGE_FILE=str(directory/'.coverage'))
 cov=coverage.Coverage(config_file=str(config));cov.combine(strict=True,keep=True);cov.save()
 sources=source_files(ROOT,args.all_sources)
 cov.json_report(morfs=sources,outfile=str(directory/'coverage.json'));cov.xml_report(morfs=sources,outfile=str(directory/'coverage.xml'));cov.html_report(morfs=sources,directory=str(directory/'html'))
 report=json.loads((directory/'coverage.json').read_text());t=report['totals']
 expected={str(Path(path).resolve()) for path in sources};measured={str((ROOT/path).resolve()) for path in report['files']}
 missing_files=sorted(expected-measured);unexpected_files=sorted(measured-expected);inventory_valid=bool(expected) and not missing_files and not unexpected_files
 summary=dict(scope='all-maintained-sources' if args.all_sources else 'application-runtime',passed=result.returncode==0,inventory_valid=inventory_valid,missing_files=missing_files,unexpected_files=unexpected_files,target_met=inventory_valid and t['missing_lines']==0 and t.get('missing_branches',0)==0,seconds=round(time.monotonic()-started,2),files=len(report['files']),lines=dict(covered=t['covered_lines'],total=t['num_statements']),branches=dict(covered=t.get('covered_branches',0),total=t.get('num_branches',0)))
 (directory/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
 return 1 if not summary['passed'] or not inventory_valid else 2 if args.check and not summary['target_met'] else 0
if __name__=='__main__':raise SystemExit(main())
