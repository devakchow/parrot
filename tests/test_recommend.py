import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PROFILES = Path(__file__).resolve().parent.parent / "profiles"


def make_repo(tmp_path, files: dict) -> Path:
    repo = tmp_path / "fixture"
    repo.mkdir()
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return repo


def recommend(repo: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "recommend_profile.py"), "--project", str(repo)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class TestRecommendation:
    def test_embedded_c_repo_hits_nasa_jpl(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "firmware/main.c": "int main(void) { return 0; }",
            "firmware/board.h": "#define LED 13",
            "linker.ld": "SECTIONS {}",
            "CMakeLists.txt": "project(fw C)\n# arm-none-eabi toolchain",
        }))
        assert out["recommended"] == "nasa-jpl"

    def test_openapi_payments_repo_hits_stripe(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "openapi.yaml": "openapi: 3.1.0",
            "src/routes/charges.ts": "export const post = () => {}",
            "package.json": json.dumps({"dependencies": {"stripe": "^14", "express": "^4"}}),
        }))
        assert out["recommended"] == "stripe"

    def test_ocaml_snapshot_repo_hits_jane_street(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "dune-project": "(lang dune 3.0)",
            "lib/engine.ml": "let x = 1",
            "lib/engine.mli": "val x : int",
            "lib/parser.ml": "let parse s = s",
            "test/__snapshots__/out.snap": "snapshot",
        }))
        assert out["recommended"] == "jane-street"

    def test_gradle_errorprone_repo_hits_palantir(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "build.gradle": "plugins { id 'com.palantir.baseline-error-prone' }\n// errorprone",
            "checkstyle.xml": "<module/>",
            "src/main/java/App.java": "class App {}",
        }))
        assert out["recommended"] == "palantir"

    def test_mobile_flags_repo_hits_meta(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "android/AndroidManifest.xml": "<manifest/>",
            "package.json": json.dumps({"dependencies": {"react-native": "0.75", "statsig": "1.0"}}),
            "src/App.tsx": "export default 1",
        }))
        assert out["recommended"] == "meta"

    def test_monorepo_markers_hit_google(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "WORKSPACE": "",
            "OWNERS": "dev",
            "svc/BUILD.bazel": "",
            "svc/main.go": "package main",
        }))
        assert out["recommended"] == "google"

    def test_no_signals_falls_back_to_google(self, tmp_path):
        out = recommend(make_repo(tmp_path, {"README.md": "# hi", "main.py": "print(1)"}))
        assert out["recommended"] == "google"
        assert all(score == 0 for score in out["scores"].values())

    def test_auth_surface_triggers_sdl_overlay(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "src/auth/login.py": "def login(): pass",
            "requirements.txt": "bcrypt\npassliB\nauthlib\n",
            "main.py": "print(1)",
        }))
        assert out["sdl_overlay"] is True

    def test_plain_repo_no_sdl(self, tmp_path):
        out = recommend(make_repo(tmp_path, {"main.py": "print(1)", "README.md": "x"}))
        assert out["sdl_overlay"] is False

    def test_evidence_is_human_readable(self, tmp_path):
        out = recommend(make_repo(tmp_path, {
            "openapi.yaml": "openapi: 3.1.0",
            "package.json": json.dumps({"dependencies": {"stripe": "^14"}}),
        }))
        assert any("stripe" in e for e in out["evidence"]["stripe"])


class TestProfileFiles:
    BASE_NAMES = {"google", "meta", "palantir", "jane-street", "nasa-jpl", "stripe"}

    def test_all_base_profiles_present_and_valid(self):
        found = {p.stem for p in PROFILES.glob("*.json")}
        assert found == self.BASE_NAMES
        for path in PROFILES.glob("*.json"):
            config = json.loads(path.read_text())
            assert config["name"] == path.stem
            assert config["schema_version"] == 1
            assert config["loop"]["max_cycles"] >= 1
            assert "builder" not in config["roles"], "builder/checker are always on, not roles"
            assert all({"id", "blocking", "description"} <= set(g) for g in config["gates"])
            assert (PROFILES / f"{path.stem}.md").exists(), f"{path.stem} missing rubric md"

    def test_overlay_valid(self):
        overlay = json.loads((PROFILES / "overlays" / "microsoft-sdl.json").read_text())
        assert overlay["type"] == "overlay"
        assert overlay["roles"]["security_auditor"] == "on"

    def test_rubric_sections_match_known_roles(self):
        known = {"builder", "checker", "planner", "spec-reviewer", "code-reviewer",
                 "security-auditor", "memory-codifier"}
        for md in list(PROFILES.glob("*.md")) + list((PROFILES / "overlays").glob("*.md")):
            roles = {line[3:].strip() for line in md.read_text().splitlines()
                     if line.startswith("## ")}
            assert roles <= known, f"{md.name} has unknown rubric sections: {roles - known}"

    def test_exactly_one_default_fallback(self):
        fallbacks = [
            path.stem for path in PROFILES.glob("*.json")
            if json.loads(path.read_text()).get("recommend", {}).get("default_fallback")
        ]
        assert fallbacks == ["google"]


class TestProfileResolution:
    def test_init_run_embeds_profile(self, state_cli, project):
        out = state_cli("init-run", "--session", "s1", "--project", str(project),
                        "--profile", "nasa-jpl", stdin="task")
        assert out["profile"] == "nasa-jpl"
        assert out["max_cycles"] == 5
        assert "security_auditor" in json.dumps(out["active_roles"]) or \
               "security_auditor" in out["active_roles"]
        state = state_cli("get-state", "--session", "s1")
        assert state["profile"]["name"] == "nasa-jpl"
        assert "builder" in state["profile"]["rubrics"]

    def test_set_profile_then_init_run_reads_it(self, state_cli, project):
        state_cli("set-profile", "--name", "stripe", "--project", str(project),
                  "--overlay", "microsoft-sdl", "--chosen-by", "recommended",
                  "--evidence", '["openapi.yaml found"]')
        choice = json.loads((project / ".parrot" / "profile.json").read_text())
        assert choice["profile"] == "stripe" and choice["overlays"] == ["microsoft-sdl"]
        out = state_cli("init-run", "--session", "s2", "--project", str(project), stdin="t")
        assert out["profile"] == "stripe"
        assert out["overlays"] == ["microsoft-sdl"]
        state = state_cli("get-state", "--session", "s2")
        gate_ids = {g["id"] for g in state["profile"]["gates"]}
        assert "secrets-scan" in gate_ids  # overlay gates merged
        assert "[overlay: microsoft-sdl]" in state["profile"]["rubrics"]["checker"]
        assert state["profile"]["roles"]["security_auditor"] == "on"

    def test_unknown_profile_fails(self, state_cli, project, plugin_data):
        import os
        import subprocess as sp
        result = sp.run(
            [sys.executable, str(SCRIPTS / "parrot_state.py"), "set-profile",
             "--name", "enron", "--project", str(project)],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
        )
        assert result.returncode == 1
        assert "unknown profile" in result.stderr

    def test_default_is_google(self, state_cli, project):
        out = state_cli("init-run", "--session", "s3", "--project", str(project), stdin="t")
        assert out["profile"] == "google"
