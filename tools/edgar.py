import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from utils.http import get_client, EDGAR_BASE, handle_api_error

# --- What is EDGAR? ---
# EDGAR (Electronic Data Gathering, Analysis, and Retrieval) is the SEC's public database
# of all filings made by US public companies. Every 10-K (annual report), 10-Q (quarterly),
# 8-K (material event), and proxy statement is available here for free.
#
# Key concept — CIK (Central Index Key):
# Every company on EDGAR has a unique numeric identifier called a CIK.
# For example, Apple's CIK is 320193. Most SEC API calls require a CIK, not a ticker.
# That's why this module has two tools: first search by name/ticker to get the CIK,
# then use the CIK to fetch filings.


class CompanySearchInput(BaseModel):
    # str_strip_whitespace: trims accidental spaces from the query string
    # extra='forbid': rejects unknown fields so Claude can't pass unexpected params
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # Accepts either a company name ("Apple") or ticker ("AAPL").
    # The search handles both via substring match on name and exact match on ticker.
    query: str = Field(
        ...,
        description="Company name or ticker (e.g., 'Apple', 'AAPL')",
        min_length=1
    )


class FilingsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # CIK must come from edgar_search_company — the SEC filing API doesn't accept tickers.
    cik: str = Field(
        ...,
        description="10-digit CIK from edgar_search_company (e.g., '0000320193')"
    )

    # Common form types:
    #   10-K   = annual report (comprehensive financials, filed once a year)
    #   10-Q   = quarterly report (abbreviated financials, filed 3x per year)
    #   8-K    = material event (filed within 4 days of something significant: earnings,
    #            acquisitions, CEO changes, etc.)
    #   DEF 14A = proxy statement (shareholder voting, executive compensation)
    # If None, all form types are returned.
    form_type: Optional[str] = Field(
        default=None,
        description="Filter by form: '10-K', '10-Q', '8-K', 'DEF 14A'"
    )

    # Default 10 is enough for most use cases. Max 40 because iterating beyond
    # that rarely adds value — the most recent filings are what matter.
    limit: Optional[int] = Field(
        default=10,
        description="Max filings to return",
        ge=1,
        le=40
    )


async def edgar_search_company_impl(params: CompanySearchInput) -> str:
    """
    Searches for a company on SEC EDGAR and returns its CIK number.

    How it works:
    The SEC publishes a single JSON file (company_tickers.json) that lists every
    publicly traded company with its CIK, ticker symbol, and name. This file covers
    all ~10,000+ SEC-registered companies and is served from the SEC's CDN.

    We download this file and do a local search rather than using EDGAR's full-text
    search API because company_tickers.json is simpler and more reliable for
    name/ticker lookups — EDGAR's search API is designed for searching filing content.

    Two match strategies:
      1. Substring match on company name (case-insensitive) — "apple" matches "Apple Inc"
      2. Exact match on ticker (case-insensitive) — "aapl" matches "AAPL"

    Returns up to 10 matches, each with:
      - cik:    10-digit zero-padded CIK (the format required by the submissions API)
      - ticker: the company's stock ticker symbol
      - name:   the company's full legal name as registered with the SEC
    """
    try:
        async with get_client() as client:
            # Download the full company registry — a flat dict keyed by an arbitrary integer,
            # where each value has: cik_str (raw CIK int), ticker (uppercase), title (name).
            resp = await client.get("https://www.sec.gov/files/company_tickers.json")
            resp.raise_for_status()
            tickers = resp.json()

        query_lower = params.query.lower()

        # Build matches using a list comprehension for efficiency on the ~10k record dataset.
        # CIK is zero-padded to 10 digits because the submissions endpoint requires that format
        # (e.g., CIK0000320193.json, not CIK320193.json).
        matches = [
            {
                "cik": f"{v['cik_str']:010d}",
                "ticker": v["ticker"],
                "name": v["title"]
            }
            for v in tickers.values()
            if query_lower in v["title"].lower() or query_lower == v["ticker"].lower()
        ][:10]  # Cap at 10 results to keep the response concise

        return json.dumps({"results": matches, "count": len(matches)}, indent=2)

    except Exception as e:
        return handle_api_error(e)


async def edgar_get_filings_impl(params: FilingsInput) -> str:
    """
    Fetches recent SEC filings for a company identified by its CIK number.

    How it works:
    The SEC's data API has a submissions endpoint that returns a company's complete
    filing history as a single JSON object. The "recent" key contains parallel arrays —
    one array per field (form type, filing date, accession number, etc.) where index i
    across all arrays describes the same filing.

    For example:
      filings["form"][0]            → "10-K"
      filings["filingDate"][0]      → "2024-11-01"
      filings["accessionNumber"][0] → "0000320193-24-000123"

    The accession number is the SEC's unique identifier for each filing and is used
    to build a direct URL to the filing folder on EDGAR's public archive.

    URL construction:
    Filing folder URLs follow this pattern:
      https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}/
    The dashes are removed from the accession number for the URL path, and the CIK
    must have its leading zeros stripped (SEC convention for archive paths).

    Form type filtering is applied client-side after fetching, because the submissions
    API doesn't support server-side filtering. The loop stops once `limit` results are
    collected, so it won't scan thousands of entries unnecessarily.
    """
    try:
        # zfill(10) ensures the CIK is 10 digits, which the submissions filename requires.
        # e.g., "320193" → "0000320193" so the URL becomes CIK0000320193.json
        cik = params.cik.zfill(10)

        async with get_client() as client:
            # The submissions endpoint returns the company's full profile including metadata
            # (name, SIC code, addresses) plus recent filing history in parallel arrays.
            resp = await client.get(f"{EDGAR_BASE}/submissions/CIK{cik}.json")
            resp.raise_for_status()
            data = resp.json()

        # "recent" contains parallel arrays of filing metadata. If a company has filed
        # more than ~1000 times, older filings appear in separate paginated files
        # referenced under data["filings"]["files"] — not handled here since recent
        # filings cover the most common use cases.
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        results = []

        for i in range(len(forms)):
            # Stop as soon as we have enough results — avoids scanning thousands of old filings
            if len(results) >= params.limit:
                break

            form = forms[i]

            # Skip filings that don't match the requested form type filter.
            # This is a client-side filter since the API doesn't support server-side filtering.
            if params.form_type and form != params.form_type:
                continue

            accession = filings["accessionNumber"][i]

            # Strip leading zeros from CIK for the archive URL — SEC uses the bare integer
            # in archive paths even though the API uses the zero-padded form.
            cik_plain = str(int(cik))

            results.append({
                "form": form,
                "filed": filings["filingDate"][i],
                "accession": accession,
                # Remove dashes from accession number to form the archive folder path.
                # e.g., "0000320193-24-000123" → "000032019324000123"
                "url": f"https://www.sec.gov/Archives/edgar/data/{cik_plain}/{accession.replace('-', '')}"
            })

        return json.dumps({
            "company": data.get("name"),
            "cik": cik,
            "filings": results,
            "count": len(results)
        }, indent=2)

    except Exception as e:
        return handle_api_error(e)
