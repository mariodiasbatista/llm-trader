"""Tests for strategies/sec_insiders.py — Form 4 XML parsing and signal filtering."""
import pytest
from unittest.mock import patch, MagicMock
from strategies.sec_insiders import (
    _is_high_conviction,
    _value_to_size_label,
    _parse_form4,
    fetch_insider_buys,
)


# ─── _is_high_conviction ──────────────────────────────────────────────────────

class TestIsHighConviction:
    def test_ceo_matches(self):
        assert _is_high_conviction("Chief Executive Officer") is True

    def test_cfo_matches(self):
        assert _is_high_conviction("Chief Financial Officer") is True

    def test_coo_matches(self):
        assert _is_high_conviction("Chief Operating Officer") is True

    def test_cto_matches(self):
        assert _is_high_conviction("Chief Technology Officer") is True

    def test_director_matches(self):
        assert _is_high_conviction("Director") is True

    def test_president_matches(self):
        assert _is_high_conviction("President") is True

    def test_chairman_matches(self):
        assert _is_high_conviction("Chairman of the Board") is True

    def test_evp_matches(self):
        assert _is_high_conviction("Executive Vice President") is True

    def test_svp_matches(self):
        assert _is_high_conviction("Senior Vice President, Finance") is True

    def test_general_counsel_matches(self):
        assert _is_high_conviction("General Counsel") is True

    def test_vp_does_not_match(self):
        assert _is_high_conviction("Vice President") is False

    def test_analyst_does_not_match(self):
        assert _is_high_conviction("Senior Analyst") is False

    def test_empty_string_returns_false(self):
        assert _is_high_conviction("") is False

    def test_none_returns_false(self):
        assert _is_high_conviction(None) is False

    def test_case_insensitive(self):
        assert _is_high_conviction("CEO") is True
        assert _is_high_conviction("ceo") is True


# ─── _value_to_size_label ─────────────────────────────────────────────────────

class TestValueToSizeLabel:
    def test_small_under_15k(self):
        assert _value_to_size_label(5_000) == "$1,001 - $15,000"

    def test_15k_to_50k(self):
        assert _value_to_size_label(30_000) == "$15,001 - $50,000"

    def test_50k_to_100k(self):
        assert _value_to_size_label(75_000) == "$50,001 - $100,000"

    def test_100k_to_250k(self):
        assert _value_to_size_label(150_000) == "$100,001 - $250,000"

    def test_250k_to_500k(self):
        assert _value_to_size_label(400_000) == "$250,001 - $500,000"

    def test_500k_to_1m(self):
        assert _value_to_size_label(750_000) == "$500,001 - $1,000,000"

    def test_1m_to_5m(self):
        assert _value_to_size_label(2_000_000) == "$1,000,001 - $5,000,000"

    def test_over_5m(self):
        assert _value_to_size_label(10_000_000) == "Over $5,000,000"

    def test_boundary_at_15k(self):
        assert _value_to_size_label(14_999) == "$1,001 - $15,000"
        assert _value_to_size_label(15_000) == "$15,001 - $50,000"


# ─── _parse_form4 helpers ─────────────────────────────────────────────────────

def _make_form4_xml(
    ticker="AAPL",
    company="Apple Inc.",
    reporter_name="John Smith",
    reporter_cik="1234567",
    officer_title="Chief Executive Officer",
    is_director="0",
    is_officer="1",
    tx_date="2026-07-10",
    shares="1000",
    price="150.00",
    tx_code="P",
    acq_disp="A",
) -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerTradingSymbol>{ticker}</issuerTradingSymbol>
    <issuerName>{company}</issuerName>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>{reporter_cik}</rptOwnerCik>
      <rptOwnerName>{reporter_name}</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>{is_director}</isDirector>
      <isOfficer>{is_officer}</isOfficer>
      <officerTitle>{officer_title}</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTransaction>
    <transactionDate><value>{tx_date}</value></transactionDate>
    <transactionCoding>
      <transactionCode>{tx_code}</transactionCode>
    </transactionCoding>
    <transactionAmounts>
      <transactionShares><value>{shares}</value></transactionShares>
      <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>{acq_disp}</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>"""


# ─── _parse_form4 ─────────────────────────────────────────────────────────────

class TestParseForm4:
    def test_returns_open_market_purchase(self):
        xml = _make_form4_xml()
        results = _parse_form4(xml, "2026-07-12")
        assert len(results) == 1
        r = results[0]
        assert r["asset"]["ticker"] == "AAPL"
        assert r["politician"]["name"] == "John Smith"
        assert r["txDate"] == "2026-07-10"
        assert r["_transaction_value"] == pytest.approx(150_000.0)
        assert r["_shares"] == 1000

    def test_skips_non_purchase_codes(self):
        for code in ["S", "A", "C", "M", "G"]:
            xml = _make_form4_xml(tx_code=code)
            assert _parse_form4(xml, "2026-07-12") == []

    def test_skips_disposition(self):
        xml = _make_form4_xml(tx_code="P", acq_disp="D")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_skips_non_director_non_officer(self):
        xml = _make_form4_xml(is_director="0", is_officer="0")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_accepts_director_without_officer(self):
        xml = _make_form4_xml(is_director="1", is_officer="0", officer_title="")
        results = _parse_form4(xml, "2026-07-12")
        assert len(results) == 1
        assert results[0]["_is_director"] is True
        assert results[0]["_insider_role"] == "Director"

    def test_boolean_field_true_string(self):
        """Some Form 4 XMLs use 'true' instead of '1' for boolean fields."""
        xml = _make_form4_xml(is_director="true", is_officer="false")
        results = _parse_form4(xml, "2026-07-12")
        assert len(results) == 1
        assert results[0]["_is_director"] is True

    def test_skips_zero_price(self):
        xml = _make_form4_xml(price="0")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_skips_zero_shares(self):
        xml = _make_form4_xml(shares="0")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_skips_missing_ticker(self):
        xml = _make_form4_xml(ticker="")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_skips_numeric_ticker(self):
        xml = _make_form4_xml(ticker="12345")
        assert _parse_form4(xml, "2026-07-12") == []

    def test_invalid_xml_returns_empty(self):
        assert _parse_form4("not xml at all", "2026-07-12") == []

    def test_high_conviction_flag_set_for_ceo(self):
        xml = _make_form4_xml(officer_title="Chief Executive Officer", is_officer="1")
        results = _parse_form4(xml, "2026-07-12")
        assert results[0]["_high_conviction"] is True

    def test_high_conviction_false_for_low_role(self):
        xml = _make_form4_xml(officer_title="Vice President of Engineering", is_officer="1")
        results = _parse_form4(xml, "2026-07-12")
        assert results[0]["_high_conviction"] is False

    def test_published_date_is_filing_date(self):
        xml = _make_form4_xml(tx_date="2026-07-10")
        results = _parse_form4(xml, "2026-07-12")
        assert results[0]["publishedDate"] == "2026-07-12"
        assert results[0]["txDate"] == "2026-07-10"

    def test_output_format_compatible_with_smart_money(self):
        """Output dict must have same top-level keys as smart_money.py output."""
        xml = _make_form4_xml()
        r = _parse_form4(xml, "2026-07-12")[0]
        assert "txDate" in r
        assert "publishedDate" in r
        assert "txType" in r
        assert "size" in r
        assert "politician" in r and "name" in r["politician"] and "id" in r["politician"]
        assert "asset" in r and "ticker" in r["asset"]

    def test_politician_id_uses_cik_prefix(self):
        xml = _make_form4_xml(reporter_cik="9876543")
        r = _parse_form4(xml, "2026-07-12")[0]
        assert r["politician"]["id"] == "CIK9876543"

    def test_multiple_transactions_in_one_filing(self):
        xml = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerTradingSymbol>MSFT</issuerTradingSymbol>
    <issuerName>Microsoft Corp</issuerName>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>111</rptOwnerCik>
      <rptOwnerName>Jane Doe</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>0</isOfficer>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-07-10</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>100</value></transactionShares>
      <transactionPricePerShare><value>400.00</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction>
  <nonDerivativeTransaction>
    <transactionDate><value>2026-07-11</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>50</value></transactionShares>
      <transactionPricePerShare><value>405.00</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction>
</ownershipDocument>"""
        results = _parse_form4(xml, "2026-07-12")
        assert len(results) == 2
        assert results[0]["_transaction_value"] == pytest.approx(40_000.0)
        assert results[1]["_transaction_value"] == pytest.approx(20_250.0)


# ─── fetch_insider_buys ───────────────────────────────────────────────────────

def _mock_signal(ticker="AAPL", tx_value=150_000, high_conviction=True, officer_title="CEO"):
    return {
        "txDate": "2026-07-10",
        "publishedDate": "2026-07-12",
        "txType": "buy",
        "size": _value_to_size_label(tx_value),
        "price": "150.00",
        "politician": {"name": "John Smith", "id": "CIK1234"},
        "asset": {"ticker": ticker, "assetName": "Test Corp", "assetType": "stock"},
        "_insider_role": officer_title,
        "_transaction_value": tx_value,
        "_shares": int(tx_value / 150),
        "_is_director": False,
        "_is_officer": True,
        "_high_conviction": high_conviction,
    }


class TestFetchInsiderBuys:
    @patch("strategies.sec_insiders._fetch_filing")
    @patch("strategies.sec_insiders._fetch_filings_metadata")
    def test_filters_by_min_transaction_value(self, mock_meta, mock_filing):
        xml_large = _make_form4_xml(shares="1000", price="200.00")   # $200K
        xml_small = _make_form4_xml(ticker="SMLL", shares="10", price="5.00")  # $50
        mock_meta.return_value = [
            ("acc1", "f1.xml", "2026-07-12", ["111"]),
            ("acc2", "f2.xml", "2026-07-12", ["222"]),
        ]
        mock_filing.side_effect = [(xml_large, "2026-07-12"), (xml_small, "2026-07-12")]

        results = fetch_insider_buys(min_transaction_value=100_000)
        tickers = [r["asset"]["ticker"] for r in results]
        assert "AAPL" in tickers
        assert "SMLL" not in tickers

    @patch("strategies.sec_insiders._fetch_filing")
    @patch("strategies.sec_insiders._fetch_filings_metadata")
    def test_filters_low_conviction_when_required(self, mock_meta, mock_filing):
        xml = _make_form4_xml(officer_title="Vice President of Engineering")
        mock_meta.return_value = [("acc1", "f1.xml", "2026-07-12", ["111"])]
        mock_filing.return_value = (xml, "2026-07-12")

        results = fetch_insider_buys(min_transaction_value=0, require_high_conviction=True)
        assert results == []

    @patch("strategies.sec_insiders._fetch_filing")
    @patch("strategies.sec_insiders._fetch_filings_metadata")
    def test_includes_low_conviction_when_not_required(self, mock_meta, mock_filing):
        xml = _make_form4_xml(officer_title="Vice President of Engineering")
        mock_meta.return_value = [("acc1", "f1.xml", "2026-07-12", ["111"])]
        mock_filing.return_value = (xml, "2026-07-12")

        results = fetch_insider_buys(min_transaction_value=0, require_high_conviction=False)
        assert len(results) == 1

    @patch("strategies.sec_insiders._fetch_filing")
    @patch("strategies.sec_insiders._fetch_filings_metadata")
    def test_skips_failed_xml_downloads(self, mock_meta, mock_filing):
        mock_meta.return_value = [
            ("acc1", "f1.xml", "2026-07-12", ["111"]),
            ("acc2", "f2.xml", "2026-07-12", ["222"]),
        ]
        mock_filing.side_effect = [(None, None), (_make_form4_xml(), "2026-07-12")]

        results = fetch_insider_buys(min_transaction_value=0)
        assert len(results) == 1

    @patch("strategies.sec_insiders._fetch_filing")
    @patch("strategies.sec_insiders._fetch_filings_metadata")
    def test_empty_metadata_returns_empty_list(self, mock_meta, mock_filing):
        mock_meta.return_value = []
        results = fetch_insider_buys()
        assert results == []
        mock_filing.assert_not_called()
