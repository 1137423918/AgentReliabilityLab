"""Compare compatible contract runs and reject misleading comparisons."""
import argparse
import json
import sys
from pathlib import Path


def compare(baseline, candidate):
    if baseline['cases_sha256'] != candidate['cases_sha256']:
        raise ValueError('Case sets differ; rerun both revisions with identical cases.')
    if baseline['scope'] != candidate['scope']:
        raise ValueError('Validation scopes differ.')
    old = {row['id']: row for row in baseline['results']}
    new = {row['id']: row for row in candidate['results']}
    if not old or old.keys() != new.keys():
        raise ValueError('Result IDs differ or are empty.')
    if len(old) != len(baseline['results']) or len(new) != len(candidate['results']):
        raise ValueError('Duplicate result IDs.')
    for key in old:
        if any(old[key].get(field) != new[key].get(field)
               for field in ('input', 'allowed_prefixes', 'expected')):
            raise ValueError('Case content differs despite matching dataset hash.')
    fixed = [key for key in old if not old[key]['passed'] and new[key]['passed']]
    regressed = [key for key in old if old[key]['passed'] and not new[key]['passed']]
    remaining = [key for key in new if not new[key]['passed']]
    return {'scope': baseline['scope'], 'cases_sha256': baseline['cases_sha256'],
            'total': len(old), 'baseline_passed': sum(row['passed'] for row in old.values()),
            'candidate_passed': sum(row['passed'] for row in new.values()),
            'fixed': fixed, 'regressed': regressed, 'remaining_failures': remaining}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['remaining_failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
