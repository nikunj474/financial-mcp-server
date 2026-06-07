import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from utils.http import get_client, FRED_BASE, FRED_KEY, handle_api_error

# --- What is FRED? ---
# FRED (Federal Reserve Economic Data) is a database maintained by the Federal Reserve
# Bank of St. Louis. It hosts 800,000+ economic time series from 100+ sources including
# the Bureau of Labor Statistics, Census Bureau, World Bank, and the Fed itself.
#
# Key concept — Series ID:
# Every dataset in FRED has a unique string identifier called a series ID.
# For example:
#   GDP       = US Gross Domestic Product (quarterly, billions of dollars)
#   FEDFUNDS  = Federal Funds Effective Rate (monthly, percent)
#   CPIAUCSL  = Consumer Price Index for All Urban Consumers (monthly, index)
#   UNRATE    = Unemployment Rate (monthly, percent)
#   DGS10     = 10-Year Treasury Constant Maturity Rate (daily, percent)
#
# Workflow: use fred_search_series to find a series ID, then fred_get_series to fetch data.


class FredSeriesInput(BaseModel):
    # str_strip_whitespace: trims accidental spaces from series IDs (e.g., " GDP" → "GDP")
    # extra='forbid': rejects unexpected fields so Claude can't pass invalid parameters
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # Series IDs are case-sensitive in FRED's API — uppercase is the convention.
    series_id: str = Field(
        ...,
        description="FRED series ID (e.g., 'GDP', 'FEDFUNDS', 'CPIAUCSL', 'UNRATE', 'DGS10')"
    )

    # Default 20 observations is enough for a quick look at recent trends.
    # Max 100 keeps response sizes manageable — FRED has series going back to the 1700s.
    limit: Optional[int] = Field(
        default=20,
        description="Number of observations to return",
        ge=1,
        le=100
    )

    # "desc" (newest first) is the default because most use cases want recent data.
    # "asc" is useful when you want to plot or analyze a trend from oldest to newest.
    sort_order: Optional[str] = Field(
        default="desc",
        description="'asc' for oldest first, 'desc' for newest first"
    )


class FredSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # Natural language search — FRED's search engine handles keyword matching.
    # Examples: "consumer price index", "federal funds rate", "housing starts"
    query: str = Field(
        ...,
        description="Search term (e.g., 'consumer price index', 'federal funds rate', 'unemployment')"
    )

    # Default 10 results is enough to find what you need. Max 30 avoids overwhelming
    # Claude with dozens of similar series (FRED has many variants of each concept).
    limit: Optional[int] = Field(default=10, ge=1, le=30)


async def fred_get_series_impl(params: FredSeriesInput) -> str:
    """
    Fetches time-series observations for a specific FRED series, along with metadata.

    Why two separate API calls?
    FRED's API separates metadata (title, units, frequency) from observations (actual data).
    We make both calls and combine them into one response so Claude has full context —
    knowing that a value is "2.3" is useless without knowing the units are "Percent" and
    the frequency is "Monthly".

    Response structure:
      - series_id:     the requested series identifier
      - title:         human-readable name (e.g., "Federal Funds Effective Rate")
      - units:         what the numbers mean (e.g., "Percent", "Billions of Dollars")
      - frequency:     how often data is reported (e.g., "Monthly", "Quarterly", "Daily")
      - last_updated:  when FRED last updated this series (useful for checking data freshness)
      - observations:  list of {date, value} pairs in the requested sort order

    Note: FRED uses "." as a placeholder for missing values (e.g., "." instead of null).
    We pass these through as-is rather than converting them, so Claude is aware of gaps.
    """
    try:
        async with get_client() as client:
            # First call: fetch series metadata only (no data points here, just descriptive info)
            meta_resp = await client.get(f"{FRED_BASE}/series", params={
                "series_id": params.series_id,
                "api_key": FRED_KEY,
                "file_type": "json"  # Without this, FRED returns XML by default
            })
            meta_resp.raise_for_status()
            # FRED wraps the result in a "seriess" array (note the unusual spelling).
            # We always get exactly one series back when querying by series_id.
            meta = meta_resp.json()["seriess"][0]

            # Second call: fetch the actual data observations (date + value pairs)
            obs_resp = await client.get(f"{FRED_BASE}/series/observations", params={
                "series_id": params.series_id,
                "api_key": FRED_KEY,
                "file_type": "json",
                "limit": params.limit,
                "sort_order": params.sort_order
            })
            obs_resp.raise_for_status()
            obs = obs_resp.json()["observations"]

        # Combine metadata + observations into a single clean response.
        # Each observation has several FRED-internal fields (realtime_start, realtime_end)
        # that we discard — only date and value are relevant here.
        return json.dumps({
            "series_id": params.series_id,
            "title": meta["title"],
            "units": meta["units"],
            "frequency": meta["frequency"],
            "last_updated": meta["last_updated"],
            "observations": [{"date": o["date"], "value": o["value"]} for o in obs]
        }, indent=2)

    except Exception as e:
        return handle_api_error(e)


async def fred_search_series_impl(params: FredSearchInput) -> str:
    """
    Searches FRED for economic data series matching a keyword query.

    This is the discovery tool — use it when you don't know the series ID yet.
    It returns a ranked list of series sorted by popularity (most-used first),
    which surfaces the canonical series for a concept before obscure variants.

    For example, searching "unemployment" returns UNRATE (the headline unemployment rate)
    before more specific series like state-level or demographic breakdowns.

    Response fields per series:
      - id:         the series ID to pass to fred_get_series (e.g., "UNRATE")
      - title:      human-readable name of the series
      - units:      what the values represent (e.g., "Percent", "Thousands of Persons")
      - frequency:  reporting cadence (e.g., "Monthly", "Quarterly", "Annual")
      - popularity: FRED's 0–100 popularity score — higher means more widely used
    """
    try:
        async with get_client() as client:
            resp = await client.get(f"{FRED_BASE}/series/search", params={
                "search_text": params.query,
                "api_key": FRED_KEY,
                "file_type": "json",
                "limit": params.limit,
                "order_by": "popularity",  # Sort by how often this series is accessed
                "sort_order": "desc"       # Most popular first
            })
            resp.raise_for_status()
            series = resp.json()["seriess"]

        # Return only the fields useful for identifying and selecting a series.
        # The full response includes dozens of fields like seasonal adjustment flags,
        # vintage dates, and realtime periods that aren't needed for discovery.
        return json.dumps({
            "query": params.query,
            "results": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "units": s["units"],
                    "frequency": s["frequency"],
                    "popularity": s["popularity"]
                }
                for s in series
            ]
        }, indent=2)

    except Exception as e:
        return handle_api_error(e)
