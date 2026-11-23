"""Prepare source-grounded dependency upgrade reviews with real OSV and uv tools.

This is a lockfile inventory and isolated resolution workflow. It does not infer
which optional dependencies are deployed, prove reachability, install the project environment,
or approve a release. uv may prepare build metadata in an isolated cache; it
does not install the project environment. Scanner exit 1 denotes findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import tomllib


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized(name):
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", name
    ):
        raise ValueError("Invalid Python package name")
    return re.sub(r"[-_.]+", "-", name).lower()


def read_toml(path):
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def inventory(lock, project):
    """Keep every resolution; markers/extras are not treated as installed state."""
    declarations = {}
    pyproject = project.get("project", {})
    groups = {"runtime": pyproject.get("dependencies", [])}
    groups.update(
        {"extra:" + k: v for k, v in pyproject.get("optional-dependencies", {}).items()}
    )
    groups.update(
        {"group:" + k: v for k, v in project.get("dependency-groups", {}).items()}
    )
    for group, requirements in groups.items():
        for requirement in requirements:
            if not isinstance(
                requirement, str
            ):  # dependency-group include objects are not requirements
                continue
            match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
            if not match:
                raise ValueError("Cannot read declared dependency name")
            name = normalized(match[1])
            declarations.setdefault(name, []).append(
                {"group": group, "requirement": requirement}
            )
    records = {}
    excluded = []
    for package in lock.get("package", []):
        name, version = normalized(package["name"]), package.get("version")
        source = package.get("source", {})
        if not isinstance(version, str) or not source.get("registry"):
            excluded.append({"name": name, "version": version, "source": source})
            continue
        key = name + "@" + version
        row = records.setdefault(
            key,
            {
                "name": name,
                "version": version,
                "sources": [],
                "declarations": declarations.get(name, []),
            },
        )
        if source not in row["sources"]:
            row["sources"].append(source)
    if not records:
        raise ValueError("No versioned registry packages in uv.lock")
    return {
        "project": normalized(pyproject["name"]),
        "packages": records,
        "nonregistry_entries": excluded,
        "scope": "All locked registry resolutions, including optional, development and conditional packages; not an installed-environment inventory.",
    }


def scanner_findings(document, locked):
    """Use OSV's matching/grouping; retain IDs and explicit coverage gaps."""
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        raise ValueError("Scanner did not return a JSON results array")
    seen, findings, nonregistry = set(), {}, []
    for result in document["results"]:
        if not isinstance(result, dict) or not isinstance(result.get("packages"), list):
            raise ValueError("Scanner package results are incomplete")
        for entry in result["packages"]:
            package = entry["package"]
            if package.get("ecosystem") != "PyPI":
                continue
            version = package.get("version")
            if version is None:
                version = ""
            if not isinstance(version, str):
                raise ValueError("Scanner package version is malformed")
            key = normalized(package["name"]) + "@" + version
            if key not in locked["packages"]:
                sources = [
                    p["source"]
                    for p in locked["nonregistry_entries"]
                    if p["name"] == normalized(package["name"])
                    and (p["version"] if p["version"] is not None else "") == version
                ]
                if not sources:
                    raise ValueError(
                        "Scanner returned a package absent from the pinned lock"
                    )
                nonregistry.append(
                    {
                        "name": normalized(package["name"]),
                        "version": version or None,
                        "sources": sources,
                        "scanner_advisory_ids": sorted(
                            {v["id"] for v in entry.get("vulnerabilities", [])}
                        ),
                        "source_bytes_audited": False,
                    }
                )
                continue
            seen.add(key)
            vulnerabilities = entry.get("vulnerabilities", [])
            if not isinstance(vulnerabilities, list):
                raise ValueError("Malformed vulnerability list")
            if not vulnerabilities:
                continue
            ids = sorted({v["id"] for v in vulnerabilities})
            groups = entry.get("groups")
            if not isinstance(groups, list) or not groups:
                raise ValueError("Vulnerable package lacks scanner advisory groups")
            grouped = {v for group in groups for v in group["ids"]}
            if not set(ids) <= grouped:
                raise ValueError("Scanner groups omit advisory records")
            findings[key] = {
                "package": locked["packages"][key]["name"],
                "version": package["version"],
                "advisory_ids": ids,
                "advisory_groups": [g["ids"] for g in groups],
                "declared_requirements": locked["packages"][key]["declarations"],
                "advisories": [
                    {
                        "id": v["id"],
                        "aliases": v.get("aliases", []),
                        "summary": v.get("summary", ""),
                        "url": "https://osv.dev/" + v["id"],
                    }
                    for v in vulnerabilities
                ],
            }
    missing = sorted(set(locked["packages"]) - seen)
    return {
        "scanned_registry_resolutions": len(seen),
        "expected_registry_resolutions": len(locked["packages"]),
        "missing_registry_resolutions": missing,
        "registry_coverage_complete": not missing,
        "affected_resolutions": len(findings),
        "unique_advisory_ids": sorted(
            {v for f in findings.values() for v in f["advisory_ids"]}
        ),
        "findings": findings,
        "nonregistry_scanner_records": nonregistry,
        "deployment_or_reachability_verified": False,
    }


def choose_target(scan):
    """Fixed policy: prefer directly declared packages, then scanner groups, then name."""
    if not scan["registry_coverage_complete"]:
        return None
    findings = scan["findings"]
    if not findings:
        return None
    return min(
        findings,
        key=lambda key: (
            not bool(findings[key]["declared_requirements"]),
            -len(findings[key]["advisory_groups"]),
            key,
        ),
    )


def compare_candidate(before, after, target_name, before_inventory, after_inventory):
    """Gate integration-test readiness; never claim production security or compatibility."""
    target_before = sorted(
        k for k, p in before_inventory["packages"].items() if p["name"] == target_name
    )
    target_after = sorted(
        k for k, p in after_inventory["packages"].items() if p["name"] == target_name
    )
    target_findings = sorted(
        k for k, f in after["findings"].items() if f["package"] == target_name
    )
    introduced = sorted(
        set(after["unique_advisory_ids"]) - set(before["unique_advisory_ids"])
    )
    old_matches = {
        (f["package"], advisory)
        for f in before["findings"].values()
        for advisory in f["advisory_ids"]
    }
    new_matches = {
        (f["package"], advisory)
        for f in after["findings"].values()
        for advisory in f["advisory_ids"]
    }
    introduced_matches = [
        {"package": name, "advisory_id": advisory}
        for name, advisory in sorted(new_matches - old_matches)
    ]
    changed = target_before != target_after
    return {
        "target_before": target_before,
        "target_after": target_after,
        "target_version_changed": changed,
        "target_affected_after": target_findings,
        "new_advisory_ids": introduced,
        "new_advisory_matches": introduced_matches,
        "remaining_affected_resolutions": after["affected_resolutions"],
        "ready_for_integration_tests": bool(
            before["registry_coverage_complete"]
            and after["registry_coverage_complete"]
            and target_after
            and changed
            and not target_findings
            and not introduced_matches
        ),
        "release_approved": False,
        "compatibility_tests_run": False,
        "all_dependency_findings_cleared": after["registry_coverage_complete"]
        and not after["affected_resolutions"],
    }


def run_tool(args, stdout, stderr, *, cwd, timeout):
    """Bound one external command and its process group, recording every exit."""
    start = time.monotonic()
    with Path(stdout).open("wb") as out, Path(stderr).open("wb") as err:
        process = subprocess.Popen(
            [str(x) for x in args],
            cwd=cwd,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    return {
        "exit_code": code,
        "timed_out": timed_out,
        "wall_seconds": round(time.monotonic() - start, 3),
    }


def scan_lock(scanner, directory, output, stem, locked, runner=run_tool):
    result = runner(
        [
            scanner,
            "scan",
            "source",
            "--format=json",
            "--all-packages",
            "--offline",
            "--no-resolve",
            "--lockfile",
            directory / "uv.lock",
        ],
        output / (stem + ".json"),
        output / (stem + ".stderr.log"),
        cwd=directory,
        timeout=300,
    )
    if result["timed_out"] or result["exit_code"] not in (0, 1):
        raise RuntimeError("OSV scan incomplete: " + json.dumps(result))
    raw = (output / (stem + ".json")).read_bytes()
    data = scanner_findings(json.loads(raw), locked)
    nonregistry_matches = any(
        p["scanner_advisory_ids"] for p in data["nonregistry_scanner_records"]
    )
    if (result["exit_code"] == 0) != (
        not data["affected_resolutions"] and not nonregistry_matches
    ):
        raise ValueError("Scanner exit status and vulnerability records disagree")
    data["receipt"] = {
        **result,
        "raw_sha256": digest(raw),
        "output_file": stem + ".json",
    }
    return data


def prepare_snapshot(
    snapshot, inputs, output, scanner, uv, python, runner=run_tool, source_repo=None
):
    directory = inputs / snapshot["id"]
    original = {name: (directory / name).read_bytes() for name in snapshot["files"]}
    for name, raw in original.items():
        if digest(raw) != snapshot["files"][name]["sha256"]:
            raise ValueError("Snapshot source bytes changed")
    locked = inventory(
        read_toml(directory / "uv.lock"), read_toml(directory / "pyproject.toml")
    )
    baseline = scan_lock(
        scanner, directory, output, snapshot["id"] + "-baseline", locked, runner
    )
    target = choose_target(baseline)
    report = {
        "snapshot": snapshot,
        "inventory": {k: v for k, v in locked.items() if k != "packages"},
        "baseline": baseline,
        "target_policy": "Direct declaration first; descending scanner group count; lexicographic key tie-break. Fixed before scans.",
        "selected_target": target,
        "candidate": None,
        "review": {"ready_for_integration_tests": False, "release_approved": False},
        "reason": "No matched findings"
        if not baseline["affected_resolutions"]
        else "Inventory coverage incomplete",
    }
    if target is not None:
        candidate = output / (snapshot["id"] + "-candidate")
        materialization = {"method": "copied-input-files", "commit": None}
        if source_repo is not None:
            prefix = snapshot["id"] + "-source-"
            commands = [
                (
                    "clone",
                    [
                        "git",
                        "clone",
                        "--no-hardlinks",
                        "--no-checkout",
                        source_repo,
                        candidate,
                    ],
                ),
                (
                    "checkout",
                    [
                        "git",
                        "-C",
                        candidate,
                        "checkout",
                        "--detach",
                        snapshot["commit"],
                    ],
                ),
                ("identity", ["git", "-C", candidate, "rev-parse", "HEAD"]),
            ]
            for phase, command in commands:
                done = runner(
                    command,
                    output / (prefix + phase + ".stdout.log"),
                    output / (prefix + phase + ".stderr.log"),
                    cwd=output,
                    timeout=120,
                )
                if done["timed_out"] or done["exit_code"] != 0:
                    raise RuntimeError("Source materialization failed: " + phase)
            if (
                output / (prefix + "identity.stdout.log")
            ).read_text().strip() != snapshot["commit"]:
                raise ValueError("Candidate Git commit differs from admitted source")
            if any(
                (candidate / name).read_bytes() != raw for name, raw in original.items()
            ):
                raise ValueError(
                    "Candidate Git source differs from the pinned metadata"
                )
            materialization = {
                "method": "independent-local-Git-clone",
                "commit": snapshot["commit"],
            }
        else:
            candidate.mkdir()
            for name, raw in original.items():
                (candidate / name).write_bytes(raw)
        readme = read_toml(candidate / "pyproject.toml")["project"].get("readme")
        readme_file = (
            readme
            if isinstance(readme, str)
            else readme.get("file")
            if isinstance(readme, dict)
            else None
        )
        if readme_file and not (candidate / readme_file).is_file():
            raise ValueError(
                "Incomplete project metadata: supply its pinned checkout with --source-repo"
            )
        name = baseline["findings"][target]["package"]
        result = runner(
            [uv, "lock", "--upgrade-package", name, "--no-build", "--python", python],
            output / (snapshot["id"] + "-resolve.stdout.log"),
            output / (snapshot["id"] + "-resolve.stderr.log"),
            cwd=candidate,
            timeout=240,
        )
        report["candidate"] = {
            "resolver": result,
            "requested_package": name,
            "original_requirements_changed": False,
            "project_environment_installed": False,
            "resolver_metadata_backend_may_run": True,
            "source_materialization": materialization,
        }
        if (candidate / "pyproject.toml").read_bytes() != original["pyproject.toml"]:
            raise ValueError("Resolver changed original declared requirements")
        if result["exit_code"] == 0 and not result["timed_out"]:
            candidate_locked = inventory(
                read_toml(candidate / "uv.lock"),
                read_toml(candidate / "pyproject.toml"),
            )
            after = scan_lock(
                scanner,
                candidate,
                output,
                snapshot["id"] + "-candidate-scan",
                candidate_locked,
                runner,
            )
            report["candidate"].update(
                scan=after, lock_sha256=digest((candidate / "uv.lock").read_bytes())
            )
            report["review"] = compare_candidate(
                baseline, after, name, locked, candidate_locked
            )
            report["reason"] = (
                "Isolated candidate resolved and rescanned; integration tests remain required."
            )
        else:
            report["reason"] = (
                "Resolution failed or timed out under unchanged project requirements; no successful upgrade is claimed."
            )
    if any((directory / name).read_bytes() != raw for name, raw in original.items()):
        raise ValueError("Original input snapshot was mutated")
    report["original_inputs_unchanged"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--database-sha256", required=True)
    parser.add_argument(
        "--source-repo", action="append", default=[], metavar="SNAPSHOT_ID=CHECKOUT"
    )
    args = parser.parse_args()
    spec = json.loads((args.inputs / "input-manifest.json").read_text())
    if digest(args.scanner.read_bytes()) != spec["scanner"]["sha256"]:
        raise ValueError("Scanner differs from the selected release digest")
    database = args.database.resolve()
    cache = database.parents[2]
    if (
        database.relative_to(cache) != Path("osv-scalibr/PyPI/all.zip")
        or digest(database.read_bytes()) != args.database_sha256
    ):
        raise ValueError("Frozen PyPI database bytes or layout differ")
    os.environ["OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"] = str(cache)
    source_repos = {}
    for value in args.source_repo:
        identifier, path = value.split("=", 1)
        if identifier in source_repos or identifier not in {
            s["id"] for s in spec["snapshots"]
        }:
            raise ValueError("Source checkout IDs must be unique admitted snapshots")
        source_repos[identifier] = Path(path).resolve()
    args.output.mkdir(mode=0o700)
    for snapshot in spec["snapshots"]:
        report = prepare_snapshot(
            snapshot,
            args.inputs,
            args.output,
            args.scanner,
            args.uv,
            args.python,
            source_repo=source_repos.get(snapshot["id"]),
        )
        report["database"] = {
            "sha256": args.database_sha256,
            "offline": True,
            "updated_during_scan": False,
        }
        if digest(database.read_bytes()) != args.database_sha256:
            raise ValueError("Offline database changed during scans")
        path = args.output / (snapshot["id"] + "-review.json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "snapshot": snapshot["id"],
                    "affected_resolutions": report["baseline"]["affected_resolutions"],
                    "selected_target": report["selected_target"],
                    "review": report["review"],
                    "reason": report["reason"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
