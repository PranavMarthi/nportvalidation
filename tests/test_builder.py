"""Tests for XML builder structure and namespace handling."""

from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT, NS_NPORTCOMMON

NS = {"n": NS_NPORT}


def _build(sample_data) -> etree._Element:
    config, filing, holdings = sample_data
    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
    return etree.fromstring(xml_bytes)


def test_root_element(sample_data):
    root = _build(sample_data)
    assert root.tag == f"{{{NS_NPORT}}}edgarSubmission"
    assert root.nsmap[None] == NS_NPORT
    assert root.nsmap["ncom"] == NS_NPORTCOMMON


def test_header(sample_data):
    root = _build(sample_data)
    assert root.find(".//n:submissionType", NS).text == "NPORT-P"
    assert root.find(".//n:isConfidential", NS).text == "false"
    assert root.find(".//n:cik", NS).text == "0002078265"


def test_gen_info(sample_data):
    root = _build(sample_data)
    gi = root.find(".//n:genInfo", NS)
    assert gi.find("n:regName", NS).text == "Corgi ETF Trust I"
    rsc = gi.find("n:regStateConditional", NS)
    assert rsc.get("regCountry") == "US"
    assert rsc.get("regState") == "US-CA"
    assert rsc.text is None


def test_fund_info(sample_data):
    root = _build(sample_data)
    fi = root.find(".//n:fundInfo", NS)
    assert fi.find("n:totAssets", NS).text == "19914806.890000000000"
    assert fi.find("n:netAssets", NS).text == "10011769.100000000000"
    mtr = root.find(".//n:monthlyTotReturn", NS)
    assert mtr.get("classId") == "C000265520"
    assert mtr.get("rtn1") == "N/A"
    assert mtr.get("rtn3") == "-1.34"


def test_holdings(sample_data):
    root = _build(sample_data)
    secs = root.findall(".//n:invstOrSec", NS)
    assert len(secs) == 54
    first = secs[0]
    assert first.find("n:name", NS).text == "MercadoLibre Inc"
    assert first.find("n:cusip", NS).text == "58733R102"
    assert first.find(".//n:isin", NS).get("value") == "US58733R1023"
    assert first.find(".//n:ticker", NS).get("value") == "MELI"


def test_signature_namespace(sample_data):
    root = _build(sample_data)
    sig = root.find(".//n:signature", NS)
    ds = sig.find(f"{{{NS_NPORTCOMMON}}}dateSigned")
    assert ds.text == "2026-02-24"
    assert sig.find(f"{{{NS_NPORTCOMMON}}}nameOfApplicant").text == "Corgi ETF Trust I"
    assert sig.find(f"{{{NS_NPORTCOMMON}}}signature").text == "/s/ Emily Yuan"
