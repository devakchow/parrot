#!/usr/bin/env python3
"""parrot profile recommender: scans a codebase and scores each profile's
recommendation signals (declared in profiles/*.json, not hardcoded here).

Prints JSON: {"scores": {...}, "recommended": "...", "sdl_overlay": bool,
"evidence": {profile: [...]}}. Stdlib only; reads manifests, never installs
or executes project code.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"

MANIFEST_NAMES = (
    "package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    "go.mod", "Cargo.toml", "Gemfile", "mix.exs", "pom.xml",
    "build.gradle", "build.gradle.kts", "composer.json", "Package.swift",
)
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".swift", ".ml", ".mli", ".hs",
    ".fs", ".ex", ".exs", ".scala", ".php", ".cs", ".ino",
}
MAX_WALK_FILES = 20000


def repo_files(project: Path) -> list:
    result = subprocess.run(
        ["git", "-C", str(project), "ls-files", "--cached", "--others",
         "--exclude-standard"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        return [line for line in result.stdout.splitlines() if line.strip()]
    files = []
    for path in project.rglob("*"):
        if len(files) >= MAX_WALK_FILES:
            break
        if path.is_file() and not any(part.startswith(".") or part == "node_modules"
                                      for part in path.relative_to(project).parts[:-1]):
            files.append(str(path.relative_to(project)))
    return files


def manifest_blob(project: Path, files: list) -> str:
    chunks = []
    for rel in files:
        if Path(rel).name in MANIFEST_NAMES:
            try:
                chunks.append((project / rel).read_text(errors="replace")[:100_000])
            except OSError:
                continue  # unreadable manifest contributes nothing
    return "\n".join(chunks).lower()


def ext_histogram(files: list) -> dict:
    counts: dict = {}
    for rel in files:
        ext = Path(rel).suffix.lower()
        if ext in CODE_EXTENSIONS:
            counts[ext] = counts.get(ext, 0) + 1
    return counts


class Facts:
    def __init__(self, project: Path):
        self.project = project
        self.files = repo_files(project)
        self.basenames = {Path(f).name for f in self.files}
        self.manifests = manifest_blob(project, self.files)
        self.exts = ext_histogram(self.files)
        self.code_total = sum(self.exts.values()) or 1


def eval_signal(signal: dict, facts: Facts):
    """Returns (hit: bool, detail: str)."""
    kind = signal.get("kind")
    if kind == "file":
        for pattern in signal["patterns"]:
            matched = [b for b in facts.basenames if fnmatch(b, pattern)]
            if matched:
                return True, f"{matched[0]} found"
    elif kind == "path_regex":
        for pattern in signal["patterns"]:
            regex = re.compile(pattern, re.IGNORECASE)
            for rel in facts.files:
                if regex.search(rel):
                    return True, f"path matches /{pattern}/ ({rel})"
    elif kind == "dep":
        for needle in signal["patterns"]:
            if needle.lower() in facts.manifests:
                return True, f"dep: {needle}"
    elif kind == "ext_share":
        count = sum(facts.exts.get(e, 0) for e in signal["extensions"])
        share = count / facts.code_total
        if share >= signal.get("min_share", 0.25):
            return True, f"{round(share * 100)}% {'/'.join(signal['extensions'])} code"
    elif kind == "file_contains":
        target = facts.project / signal["file"]
        if target.exists():
            try:
                if signal["needle"] in target.read_text(errors="replace"):
                    return True, f"{signal['file']} contains {signal['needle']}"
            except OSError:
                pass  # unreadable file is a non-hit, not an error
    return False, ""


def score_profile(config: dict, facts: Facts):
    score, evidence = 0, []
    for signal in config.get("recommend", {}).get("signals", []):
        hit, detail = eval_signal(signal, facts)
        if hit:
            score += signal.get("weight", 1)
            evidence.append(f"{detail} ({signal.get('evidence', signal.get('kind'))})")
    return score, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    args = parser.parse_args()
    facts = Facts(Path(args.project).resolve())

    scores, evidence, fallback = {}, {}, "google"
    for path in sorted(PROFILES_DIR.glob("*.json")):
        config = json.loads(path.read_text())
        name = config["name"]
        scores[name], evidence[name] = score_profile(config, facts)
        if config.get("recommend", {}).get("default_fallback"):
            fallback = name

    overlay_path = PROFILES_DIR / "overlays" / "microsoft-sdl.json"
    overlay = json.loads(overlay_path.read_text())
    sdl_score, sdl_evidence = score_profile(overlay, facts)
    sdl = sdl_score >= 3
    if sdl:
        evidence["microsoft-sdl"] = sdl_evidence

    best = max(scores, key=lambda name: scores[name])
    recommended = best if scores[best] > 0 else fallback

    print(json.dumps({
        "scores": scores,
        "recommended": recommended,
        "sdl_overlay": sdl,
        "evidence": {k: v for k, v in evidence.items() if v},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
