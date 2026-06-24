"""CLI integration tests."""

import pytest

import nport.cli as climod
from nport.cli import main


class TestBuildAllFunds:
    def test_no_fund_builds_every_fund_with_filing(self, monkeypatch, tmp_path):
        funds = tmp_path / "funds"
        for t in ("aaa", "bbb"):
            (funds / t / "filings" / "2026-06").mkdir(parents=True)
            (funds / t / "fund_config.txt").write_text("x")
            (funds / t / "filings" / "2026-06" / "filing_data.txt").write_text("x")
        (funds / "nofiling").mkdir()                       # no period filing → skipped
        (funds / "nofiling" / "fund_config.txt").write_text("x")
        monkeypatch.setattr(climod, "_DEFAULT_FUNDS_DIR", funds)
        seen = []
        monkeypatch.setattr(climod, "_ingest_one", lambda args: seen.append(args.pos[0]))
        main(["build", "2026-06"])
        assert sorted(seen) == ["AAA", "BBB"]

    def test_named_fund_routes_to_single(self, monkeypatch):
        called = {}
        monkeypatch.setattr(climod, "_ingest_one", lambda args: called.setdefault("pos", args.pos))
        main(["build", "fdrs", "2026-06"])
        assert called["pos"] == ["fdrs", "2026-06"]


def _fdrs_paths(fdrs_dir):
    return {
        "config": str(fdrs_dir / "fund_config.txt"),
        "filing": str(fdrs_dir / "filings" / "2025-12" / "filing_data.txt"),
        "holdings": str(fdrs_dir / "filings" / "2025-12" / "holdings.csv"),
    }


class TestGenerate:
    def test_succeeds(self, fdrs_dir, tmp_path):
        p = _fdrs_paths(fdrs_dir)
        out = tmp_path / "out.xml"
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(out), "--skip-schema-check"])
        assert out.exists()
        assert "edgarSubmission" in out.read_text()

    def test_verbose(self, fdrs_dir, tmp_path, capsys):
        p = _fdrs_paths(fdrs_dir)
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(tmp_path / "out.xml"),
              "--skip-schema-check", "--verbose"])
        assert "54 holdings" in capsys.readouterr().out

    def test_creates_parent_dirs(self, fdrs_dir, tmp_path):
        p = _fdrs_paths(fdrs_dir)
        out = tmp_path / "a" / "b" / "out.xml"
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(out), "--skip-schema-check", "--skip-validation"])
        assert out.exists()

    @pytest.mark.parametrize("missing", ["config", "filing", "holdings"])
    def test_missing_file_exits(self, fdrs_dir, tmp_path, missing):
        paths = _fdrs_paths(fdrs_dir)
        paths[missing] = "/nonexistent"
        with pytest.raises(SystemExit):
            main(["generate", "--config", paths["config"],
                  "--filing", paths["filing"], "--holdings", paths["holdings"],
                  "--output", str(tmp_path / "out.xml"), "--skip-schema-check"])


class TestValidate:
    def test_passes(self, fdrs_dir, capsys):
        p = _fdrs_paths(fdrs_dir)
        main(["validate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"]])
        assert "PASSED" in capsys.readouterr().out


class TestNoCommand:
    def test_exits(self):
        with pytest.raises(SystemExit):
            main([])
