from pathlib import Path
import json,os
ROOT=Path(os.environ['COMPAT_REPORT_ROOT'])
def pytest_collection_finish(session):
 (ROOT/'collection.json').write_text(json.dumps([item.nodeid for item in session.items])+"\n")
def pytest_runtest_logreport(report):
 with (ROOT/'outcomes.jsonl').open('a') as f:f.write(json.dumps({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome})+"\n")
