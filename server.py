from mcp.server.fastmcp import FastMCP
from tools.edgar import (CompanySearchInput, FilingsInput,
                          edgar_search_company_impl, edgar_get_filings_impl)
from tools.fred import (FredSeriesInput, FredSearchInput,
                         fred_get_series_impl, fred_search_series_impl)
from tools.market import (TickerInput, market_get_quote_impl, market_get_overview_impl)


# --- What is this server? ---
# This is an MCP (Model Context Protocol) server that gives Claude access to live
# financial data from three sources:
#   1. SEC EDGAR  — public company filings (10-K, 10-Q, 8-K, proxy statements)
#   2. FRED       — macroeconomic time series (GDP, inflation, interest rates, etc.)
#   3. Alpha Vantage — real-time stock quotes and company fundamentals
#
# How MCP works:
# Claude calls tools by name with structured JSON inputs. FastMCP handles the
# protocol layer — it advertises available tools, validates inputs against the
# Pydantic models, and routes each call to the right Python function.
#
# The actual implementation lives in tools/ — this file just wires up the routes.

# Create the MCP server instance. The name "financial_mcp" is what appears in
# Claude Desktop's connected tools list and in MCP logs.
mcp = FastMCP("financial_mcp")


# =============================================================================
# SEC EDGAR TOOLS
# =============================================================================
# These two tools work together in sequence:
#   Step 1: edgar_search_company  → find the company's CIK number
#   Step 2: edgar_get_filings     → use the CIK to fetch actual filings
#
# Why two steps? The SEC's filing API requires a CIK (their internal ID), not a
# ticker. The search step resolves a human-readable name or ticker into a CIK.

@mcp.tool(
    name="edgar_search_company",
    annotations={
        "readOnlyHint": True,      # This tool never writes or modifies any data
        "destructiveHint": False,  # No side effects
        "idempotentHint": True     # Same input always returns the same result
    }
)
async def edgar_search_company(params: CompanySearchInput) -> str:
    """Search SEC EDGAR for a company by name or ticker. Returns CIK numbers needed
    for edgar_get_filings. Example: query='Apple' or query='AAPL'."""
    return await edgar_search_company_impl(params)


@mcp.tool(
    name="edgar_get_filings",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True     # Filing history doesn't change (new filings append; old ones stay)
    }
)
async def edgar_get_filings(params: FilingsInput) -> str:
    """Get recent SEC filings for a company using its CIK. Supports filtering by form type
    (10-K annual report, 10-Q quarterly, 8-K material events, DEF 14A proxy).
    Returns filing dates, accession numbers, and direct URLs."""
    return await edgar_get_filings_impl(params)


# =============================================================================
# FRED ECONOMIC DATA TOOLS
# =============================================================================
# These two tools also work together in sequence:
#   Step 1: fred_search_series  → discover series IDs by keyword
#   Step 2: fred_get_series     → fetch actual observations using a series ID
#
# FRED has 800,000+ series, so the search step is essential when you don't
# already know the exact series ID (e.g., "GDP", "UNRATE", "FEDFUNDS").

@mcp.tool(
    name="fred_search_series",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True
    }
)
async def fred_search_series(params: FredSearchInput) -> str:
    """Search the FRED database for economic data series by keyword. Returns series IDs,
    titles, units, and frequency. Use series IDs with fred_get_series to fetch data.
    Common series: GDP, FEDFUNDS, CPIAUCSL, UNRATE, DGS10 (10-yr Treasury)."""
    return await fred_search_series_impl(params)


@mcp.tool(
    name="fred_get_series",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True
    }
)
async def fred_get_series(params: FredSeriesInput) -> str:
    """Fetch observations for a FRED economic data series. Returns time-series values
    with dates and units. Use sort_order='desc' for most recent data first."""
    return await fred_get_series_impl(params)


# =============================================================================
# MARKET DATA TOOLS
# =============================================================================
# These two tools are independent — either can be called directly with just a ticker.
#   market_get_quote    → real-time price snapshot (changes every second during market hours)
#   market_get_overview → company fundamentals (updated quarterly from financial statements)

@mcp.tool(
    name="market_get_quote",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False    # NOT idempotent — stock price changes between calls
    }
)
async def market_get_quote(params: TickerInput) -> str:
    """Get the latest stock quote for a ticker: price, change, volume, and previous close."""
    return await market_get_quote_impl(params)


@mcp.tool(
    name="market_get_overview",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True     # Fundamentals update quarterly, stable within a session
    }
)
async def market_get_overview(params: TickerInput) -> str:
    """Get company fundamentals: sector, P/E ratio, EPS, revenue, profit margin,
    52-week range, analyst target price, and business description."""
    return await market_get_overview_impl(params)


if __name__ == "__main__":
    # Start the MCP server using stdio transport.
    # Claude Desktop communicates with this process over stdin/stdout using the MCP protocol.
    # To connect it, add this server to your claude_desktop_config.json with the path to
    # this file and the Python interpreter from the .venv environment.
    mcp.run()
