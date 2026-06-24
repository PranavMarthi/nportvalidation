"""Tests for schema file checking and version monitoring."""

from nport.schema_check import (
    CURRENT_SCHEMA_VERSION,
    EXPECTED_SCHEMA_FILES,
    check_schema_files,
    get_schema_integrity_report,
)


class TestCheckFiles:
    def test_valid_dir(self, schema_dir):
        assert check_schema_files(schema_dir)[0] == []

    def test_missing_dir(self, tmp_path):
        errors, _ = check_schema_files(tmp_path / "nope")
        assert len(errors) == 1 and "not found" in errors[0]

    def test_missing_single_file(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        for f in EXPECTED_SCHEMA_FILES[1:]:
            (d / f).write_text("<xs:schema/>")
        errors, _ = check_schema_files(d)
        assert len(errors) == 1 and EXPECTED_SCHEMA_FILES[0] in errors[0]

    def test_empty_file(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        for f in EXPECTED_SCHEMA_FILES:
            (d / f).write_text("")
        errors, _ = check_schema_files(d)
        assert len(errors) == len(EXPECTED_SCHEMA_FILES)

    def test_all_files_present(self, schema_dir):
        for f in EXPECTED_SCHEMA_FILES:
            assert (schema_dir / f).exists()


class TestIntegrityReport:
    def test_structure(self, schema_dir):
        r = get_schema_integrity_report(schema_dir)
        assert r["schema_version"] == CURRENT_SCHEMA_VERSION
        for f in EXPECTED_SCHEMA_FILES:
            assert r["files"][f]["size"] > 0
            assert len(r["files"][f]["sha256"]) == 64

    def test_missing_dir(self, tmp_path):
        r = get_schema_integrity_report(tmp_path / "nope")
        assert all(r["files"][f] == {"missing": True} for f in EXPECTED_SCHEMA_FILES)
