import os
import httpx
from dotenv import load_dotenv

# Load environment variables from a .env file in the project root.
# This lets developers store API keys locally without hardcoding them.
# If no .env file exists, os.getenv() calls below will return None (or the default).
load_dotenv()

# --- API Keys ---
# These keys authenticate requests to external financial data APIs.
# They must be set in your .env file before the server will work:
#   ALPHA_VANTAGE_API_KEY=your_key_here   (free at alphavantage.co)
#   FRED_API_KEY=your_key_here            (free at fred.stlouisfed.org)
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
FRED_KEY = os.getenv("FRED_API_KEY")

# SEC EDGAR does not require an API key, but the SEC requires all automated
# requests to include a User-Agent header identifying who is making the request.
# Failure to set this can result in your IP being blocked by the SEC.
# Format: "AppName ContactEmail" — set SEC_USER_AGENT in your .env to customize it.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Financial MCP Server contact@example.com")

# --- Base URLs ---
# Centralizing these here means if an API changes its URL, there's only one place to update.
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"   # All Alpha Vantage endpoints use this base with a ?function= param
FRED_BASE = "https://api.stlouisfed.org/fred"              # St. Louis Fed economic data API
EDGAR_BASE = "https://data.sec.gov"                        # SEC's machine-readable data API (no rate limit key needed)


def get_client() -> httpx.AsyncClient:
    """
    Creates and returns an async HTTP client configured for all financial API calls.

    Why async? The MCP server is async, and using httpx.AsyncClient lets multiple
    tool calls run concurrently without blocking each other.

    Why a 30s timeout? External financial APIs can be slow, especially EDGAR which
    serves large JSON files. 30s is generous enough to handle slow responses while
    still failing fast if the API is completely down.

    Why set User-Agent on every request? The SEC EDGAR API requires it and will
    return 403 Forbidden without it. Setting it globally ensures EDGAR calls always
    include it, even if future code doesn't think to add it manually.

    Usage: `async with get_client() as client:` — the context manager ensures
    the underlying TCP connections are properly closed after the request.
    """
    return httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": SEC_USER_AGENT}
    )


def handle_api_error(e: Exception) -> str:
    """
    Converts HTTP errors and network failures into plain-English strings.

    MCP tools must return strings, not raise exceptions — Claude can't catch
    exceptions from tools. So every tool wraps its logic in try/except and
    calls this function to produce a user-readable error message.

    Handled cases:
      - 404: The ticker, CIK, or series ID doesn't exist in the API
      - 429: Too many requests — free-tier APIs (Alpha Vantage, FRED) have rate limits
      - 403: Bad or missing API key, or SEC blocked the User-Agent
      - Other HTTP status: Catch-all for unexpected API errors
      - Timeout: API took longer than 30s to respond
      - Anything else: Unexpected Python exception (e.g., JSON parse error, network down)
    """
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 404:
            return "Error: Resource not found. Check the ticker or series ID."
        elif e.response.status_code == 429:
            return "Error: Rate limit hit. Wait a moment and retry."
        elif e.response.status_code == 403:
            return "Error: Access denied. Check your API key."
        return f"Error: API returned status {e.response.status_code}"
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Try again."
    # Catch-all: include the exception type so the error is debuggable
    return f"Error: {type(e).__name__}: {str(e)}"
