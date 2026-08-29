"""EDGAR tool behaviour, with the network stubbed out.

The two things worth pinning down here are the CIK zero-padding and the
archive URL construction: both are SEC conventions that are easy to get
subtly wrong and impossible to notice without a test."""
import tools.edgar as edgar
from tools.edgar import (CompanySearchInput, FilingsInput,
                         edgar_get_filings_impl, edgar_search_company_impl)

from conftest import loads


async def test_search_matches_on_name_substring(patch_client, company_tickers):
    patch_client(edgar, company_tickers)
    out = loads(await edgar_search_company_impl(CompanySearchInput(query="apple")))
    assert out["count"] == 1
    assert out["results"][0]["ticker"] == "AAPL"


async def test_search_matches_on_exact_ticker(patch_client, company_tickers):
    patch_client(edgar, company_tickers)
    out = loads(await edgar_search_company_impl(CompanySearchInput(query="nvda")))
    assert out["results"][0]["name"] == "NVIDIA CORP"


async def test_search_pads_cik_to_ten_digits(patch_client, company_tickers):
    """The submissions endpoint 404s on an unpadded CIK."""
    patch_client(edgar, company_tickers)
    out = loads(await edgar_search_company_impl(CompanySearchInput(query="apple")))
    assert out["results"][0]["cik"] == "0000320193"


async def test_search_returns_empty_rather_than_erroring(patch_client, company_tickers):
    patch_client(edgar, company_tickers)
    out = loads(await edgar_search_company_impl(CompanySearchInput(query="zzzz")))
    assert out == {"results": [], "count": 0}


async def test_filings_filters_by_form_type(patch_client, apple_submissions):
    patch_client(edgar, apple_submissions)
    out = loads(await edgar_get_filings_impl(
        FilingsInput(cik="0000320193", form_type="10-K")))
    assert out["count"] == 2
    assert {f["form"] for f in out["filings"]} == {"10-K"}


async def test_filings_respects_limit(patch_client, apple_submissions):
    patch_client(edgar, apple_submissions)
    out = loads(await edgar_get_filings_impl(FilingsInput(cik="0000320193", limit=2)))
    assert out["count"] == 2


async def test_filings_builds_archive_url_without_dashes(patch_client, apple_submissions):
    """Archive paths use a bare CIK and a dashless accession number."""
    patch_client(edgar, apple_submissions)
    out = loads(await edgar_get_filings_impl(
        FilingsInput(cik="0000320193", form_type="10-K", limit=1)))
    assert out["filings"][0]["url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000123"
    )


async def test_filings_pads_short_cik_before_requesting(patch_client, apple_submissions):
    client = patch_client(edgar, apple_submissions)
    await edgar_get_filings_impl(FilingsInput(cik="320193"))
    assert client.requested_urls[0].endswith("/submissions/CIK0000320193.json")


async def test_filings_surfaces_upstream_404_as_a_message(patch_client, apple_submissions):
    """Tools must return strings, never raise: the model cannot catch exceptions."""
    patch_client(edgar, apple_submissions, status_code=404)
    out = await edgar_get_filings_impl(FilingsInput(cik="9999999999"))
    assert out.startswith("Error:")
    assert "not found" in out.lower()
