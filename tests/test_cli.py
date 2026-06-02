"""CLI integration tests."""

import pytest
from nport.cli import main


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
