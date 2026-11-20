"""Run path contracts against a trusted prepared module and emit raw evidence."""
import argparse
import hashlib
import importlib.util
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_case(function, case):
    options = {'allowed_prefixes': case['allowed_prefixes']} if 'allowed_prefixes' in case else {}
    try:
        observed = {'value': function(case['input'], **options)}
    except ValueError as error:
        observed = {'error': type(error).__name__, 'message': str(error)}
    except Exception as error:
        observed = {'unexpected_error': type(error).__name__, 'message': str(error)}
    expected = case['expected']
    passed = (observed.get('error') == expected['error']) if 'error' in expected else observed == expected
    return {**case, 'observed': observed, 'passed': passed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', required=True, type=Path)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        cases = json.loads(args.cases.read_text())
        ids = [case['id'] for case in cases]
        if not cases or len(ids) != len(set(ids)):
            raise ValueError('Cases must be nonempty with unique IDs.')
        spec = importlib.util.spec_from_file_location('contract_subject', args.module)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        results = [run_case(module.validate_path, case) for case in cases]
    except (OSError, ValueError, ImportError, AttributeError, KeyError, TypeError) as error:
        parser.error(str(error))
    passed = sum(item['passed'] for item in results)
    report = {'schema_version': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'isolated upstream path functions; no model or package integration',
              'python': platform.python_version(), 'platform': platform.platform(),
              'module_sha256': hashlib.sha256(args.module.read_bytes()).hexdigest(),
              'cases_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              'total': len(results), 'passed': passed, 'failed': len(results) - passed, 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('scope', 'total', 'passed', 'failed')}, ensure_ascii=False))
    for result in results:
        if not result['passed']:
            print(json.dumps(result, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
