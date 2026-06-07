import json
from pydantic import BaseModel, Field, ConfigDict
from utils.http import get_client, ALPHA_VANTAGE_BASE, ALPHA_VANTAGE_KEY, handle_api_error

# --- Input Validation ---
# Pydantic models validate and sanitize tool inputs before any API call is made.
# FastMCP uses these models to auto-generate the JSON schema that Claude sees,
# so the Field descriptions here are what Claude reads to understand each parameter.

class TickerInput(BaseModel):
    # str_strip_whitespace: automatically trims leading/trailing spaces from the ticker
    # extra='forbid': rejects any unexpected fields — prevents Claude from passing garbage params
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    # The `...` means this field is required (no default).
    # min_length=1 prevents empty strings; max_length=10 covers the longest valid tickers.
    ticker: str = Field(
        ...,
        description="Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'NVDA')",
        min_length=1,
        max_length=10
    )


async def market_get_quote_impl(params: TickerInput) -> str:
    """
    Fetches the latest real-time stock quote for a given ticker from Alpha Vantage.

    Alpha Vantage's GLOBAL_QUOTE function returns a single snapshot of the stock's
    current trading state: price, change from previous close, volume, etc.

    Why is idempotentHint=False on the MCP tool? Stock prices change every second
    during market hours, so the same call at different times returns different data.
    This tells Claude not to assume it can cache or reuse a previous result.

    Response fields explained:
      - price:             current market price per share
      - change:            dollar change from the previous close
      - change_pct:        percentage change (e.g., "1.23%")
      - volume:            number of shares traded today
      - latest_trading_day: the date of the most recent trading session
      - prev_close:        the closing price from the prior trading day
    """
    try:
        async with get_client() as client:
            # Alpha Vantage uses a single base URL with a `function` query param to select
            # the data type. GLOBAL_QUOTE is the simplest real-time quote endpoint.
            resp = await client.get(ALPHA_VANTAGE_BASE, params={
                "function": "GLOBAL_QUOTE",
                "symbol": params.ticker,
                "apikey": ALPHA_VANTAGE_KEY
            })
            resp.raise_for_status()  # Raise an exception for 4xx/5xx HTTP status codes

            # The API wraps quote data in a "Global Quote" key. If it's missing or empty,
            # the ticker is likely invalid or not listed on a supported exchange.
            data = resp.json().get("Global Quote", {})
            if not data:
                return f"Error: No quote data found for {params.ticker}. Check the ticker symbol."

        # Alpha Vantage uses odd numbered keys like "05. price" instead of clean names.
        # We remap them here to readable keys before returning to Claude.
        return json.dumps({
            "ticker": params.ticker,
            "price": data.get("05. price"),
            "change": data.get("09. change"),
            "change_pct": data.get("10. change percent"),
            "volume": data.get("06. volume"),
            "latest_trading_day": data.get("07. latest trading day"),
            "prev_close": data.get("08. previous close"),
        }, indent=2)

    except Exception as e:
        return handle_api_error(e)


async def market_get_overview_impl(params: TickerInput) -> str:
    """
    Fetches company fundamentals and financial metrics from Alpha Vantage's OVERVIEW endpoint.

    Unlike market_get_quote (which is real-time), OVERVIEW data is updated less frequently
    (roughly quarterly) and contains longer-term metrics derived from financial statements.

    This is useful for understanding a company's valuation, size, profitability, and
    what business it's actually in — context that a stock price alone doesn't provide.

    Response fields explained:
      - market_cap:     total market capitalization in USD
      - pe_ratio:       price-to-earnings ratio (how expensive the stock is relative to earnings)
      - eps:            earnings per share (trailing twelve months)
      - revenue_ttm:    total revenue over the trailing twelve months
      - profit_margin:  net profit margin as a decimal (e.g., 0.25 = 25%)
      - 52w_high/low:   the highest and lowest price in the past 52 weeks
      - analyst_target: the average analyst price target
      - description:    a plain-English summary of what the company does (capped at 500 chars
                        to keep the response from being overwhelming for Claude's context)
    """
    try:
        async with get_client() as client:
            # OVERVIEW returns a flat JSON object (no nesting) with dozens of fields.
            resp = await client.get(ALPHA_VANTAGE_BASE, params={
                "function": "OVERVIEW",
                "symbol": params.ticker,
                "apikey": ALPHA_VANTAGE_KEY
            })
            resp.raise_for_status()
            d = resp.json()

            # If the response is empty or missing "Symbol", the ticker wasn't found.
            # Alpha Vantage returns an empty {} for unknown tickers instead of a 404.
            if not d or "Symbol" not in d:
                return f"Error: No overview data for {params.ticker}."

        # Select only the most useful fields — the full response has 50+ fields,
        # most of which are redundant or rarely needed.
        return json.dumps({
            "ticker": d.get("Symbol"),
            "name": d.get("Name"),
            "sector": d.get("Sector"),
            "industry": d.get("Industry"),
            "market_cap": d.get("MarketCapitalization"),
            "pe_ratio": d.get("PERatio"),
            "eps": d.get("EPS"),
            "revenue_ttm": d.get("RevenueTTM"),
            "profit_margin": d.get("ProfitMargin"),
            "52w_high": d.get("52WeekHigh"),
            "52w_low": d.get("52WeekLow"),
            "analyst_target": d.get("AnalystTargetPrice"),
            # Truncate description to 500 chars — it can be several paragraphs long
            "description": d.get("Description", "")[:500]
        }, indent=2)

    except Exception as e:
        return handle_api_error(e)
