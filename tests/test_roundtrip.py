"""Round-trip test: generate XML from sample inputs and compare to reference filing.

The generated XML must match the reference filing (FDRS Dec 2025, accession
0000894189-26-004341) exactly — same elements, same text, same attributes,
same ordering. This is the primary acceptance criterion.

The sample fixture defaults `liveTestFlag=TEST` for operational safety, but the
reference filing was submitted LIVE (EDGAR omits the element on live filings),
so these tests override the flag to LIVE before generating.
"""

from dataclasses import replace

from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT
from nport.xsd_validator import NportValidator


def _as_filed(sample_data):
    """Return sample data with liveTestFlag set to LIVE, matching the reference."""
    config, filing, holdings = sample_data
    return config, replace(filing, live_test_flag="LIVE"), holdings


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _compare_elements(gen_el, ref_el, path="") -> list[str]:
    """Recursively compare two XML elements. Returns list of differences."""
    diffs = []
    current = f"{path}/{_strip_ns(gen_el.tag)}"

    if gen_el.tag != ref_el.tag:
        diffs.append(f"{current}: tag mismatch: {gen_el.tag} vs {ref_el.tag}")
        return diffs

    gen_text = (gen_el.text or "").strip()
    ref_text = (ref_el.text or "").strip()
    if gen_text != ref_text:
        diffs.append(f"{current}: text mismatch: {gen_text!r} vs {ref_text!r}")

    if dict(gen_el.attrib) != dict(ref_el.attrib):
        diffs.append(f"{current}: attr mismatch: {dict(gen_el.attrib)} vs {dict(ref_el.attrib)}")

    gen_children = list(gen_el)
    ref_children = list(ref_el)

    if len(gen_children) != len(ref_children):
        diffs.append(
            f"{current}: child count mismatch: "
            f"{len(gen_children)} vs {len(ref_children)}"
        )
    for i, (gc, rc) in enumerate(zip(gen_children, ref_children)):
        diffs.extend(_compare_elements(gc, rc, f"{current}[{i}]"))

    return diffs


def test_xsd_validation(sample_data, schema_dir):
    config, filing, holdings = _as_filed(sample_data)
    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
    errors = NportValidator(schema_dir).validate_xsd(xml_bytes)
    assert errors == [], "XSD errors:\n" + "\n".join(errors)


def test_exact_match_reference_filing(sample_data, reference_xml):
    """Every element, text value, and attribute must be identical."""
    config, filing, holdings = _as_filed(sample_data)
    gen_root = etree.fromstring(NportBuilder(config, filing, holdings).to_xml_bytes())
    ref_root = etree.parse(str(reference_xml)).getroot()
    diffs = _compare_elements(gen_root, ref_root)
    assert diffs == [], (
        f"{len(diffs)} difference(s):\n" + "\n".join(diffs)
    )


def test_every_holding_matches(sample_data, reference_xml):
    """Compare each holding individually for targeted error reporting."""
    ns = {"n": NS_NPORT}
    config, filing, holdings = _as_filed(sample_data)
    gen_root = etree.fromstring(NportBuilder(config, filing, holdings).to_xml_bytes())
    ref_root = etree.parse(str(reference_xml)).getroot()

    gen_secs = gen_root.findall(".//n:invstOrSec", ns)
    ref_secs = ref_root.findall(".//n:invstOrSec", ns)
    assert len(gen_secs) == len(ref_secs) == 54

    for i, (gs, rs) in enumerate(zip(gen_secs, ref_secs)):
        name = (gs.find("n:name", ns).text or f"[{i}]")
        diffs = _compare_elements(gs, rs)
        assert diffs == [], f"Holding '{name}':\n" + "\n".join(diffs)
