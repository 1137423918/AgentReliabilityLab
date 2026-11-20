"""Prepare exact upstream function slices for dependency-free reproduction."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    relative = 'libs/deepagents/deepagents/backends/utils.py'
    source = (args.checkout / relative).read_text()
    names = ('to_posix_path', 'validate_path')
    functions = {node.name: ast.get_source_segment(source, node)
                 for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name in names}
    if set(functions) != set(names):
        parser.error('Expected upstream functions were not found; inspect the baseline.')
    header = 'import os\nimport re\nfrom pathlib import PurePosixPath\nfrom collections.abc import Sequence\n\n'
    module = header + '\n\n'.join(functions[name] for name in names) + '\n'
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'baseline.py').write_text(module)
    commit = subprocess.check_output(['git', '-C', str(args.checkout), 'rev-parse', 'HEAD'], text=True).strip()
    metadata = {'upstream': 'https://github.com/langchain-ai/deepagents', 'commit': commit,
                'file': relative, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'slice_sha256': hashlib.sha256(module.encode()).hexdigest(),
                'functions': list(names), 'scope': 'isolated exact source functions; no package integration'}
    (args.out / 'provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
