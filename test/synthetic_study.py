"""Synthetic study records for isolated SQL and browser integration checks."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'jumpserve-back-end'
sys.path.insert(0, str(BACKEND / 'research_workflow'))
import preparation
import workflow

def study_fixture(study_id):
    raw = (BACKEND / 'research_workflow/tests/fixtures/preparation/synthetic-plan.json').read_bytes()
    plan = preparation.parse(raw)
    compiled = preparation.compile_plan(plan, raw, {'id': study_id, 'paper_url': plan['paper_urls'][0]})
    paper = workflow.paper_details(dict(title='Synthetic software study', paper_url=plan['paper_urls'][0],
        domain='Software verification', scope='Generated isolated test data; no research claims', origin_module=None))
    return dict(paper=paper, records=compiled['records'], provenance=dict(synthetic=True, scientific_evidence=False))
