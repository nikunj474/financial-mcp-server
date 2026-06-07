# 📊 Financial MCP Server

> A [Model Context Protocol](https://modelcontextprotocol.io) server that gives any MCP-compatible AI client — Claude, GPT, Gemini — live access to SEC filings, Federal Reserve economic data, and stock market fundamentals.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![MCP Protocol](https://img.shields.io/badge/MCP-2025--11--25-green.svg)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

Ask Claude questions like:

> *"Pull Apple's latest 10-K filing and compare their cash position against the current Fed funds rate trend."*

Claude will autonomously chain three tools — searching EDGAR for the CIK, fetching the filing, pulling FRED macro data — and synthesize a structured answer. No manual API calls, no copy-pasting between tabs.

**Data sources:**

| Source | What You Get | API Key Required |
|--------|-------------|-----------------|
| [SEC EDGAR](https://www.sec.gov/developer) | Company filings: 10-K, 10-Q, 8-K, DEF 14A | No |
| [FRED](https://fred.stlouisfed.org/docs/api/) | 800K+ economic series: GDP, CPI, Fed funds rate, yield curves | Yes (free) |
| [Alpha Vantage](https://www.alphavantage.co/) | Stock quotes, P/E ratio, EPS, revenue, analyst targets | Yes (free) |

---

## Tools

| Tool | Description | Example Input |
|------|-------------|---------------|
| `edgar_search_company` | Search EDGAR for a company by name or ticker — returns CIK | `query: "Apple"` |
| `edgar_get_filings` | List recent filings for a CIK with direct URLs | `cik: "0000320193", form_type: "10-K"` |
| `fred_search_series` | Search FRED's 800K+ economic series by keyword | `query: "federal funds rate"` |
| `fred_get_series` | Fetch time-series observations for a FRED series | `series_id: "FEDFUNDS", limit: 12` |
| `market_get_quote` | Live stock quote: price, change, volume | `ticker: "NVDA"` |
| `market_get_overview` | Company fundamentals: P/E, EPS, revenue, margins | `ticker: "MSFT"` |

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/nikunj474/financial-mcp-server.git
cd financial-mcp-server

uv venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 2. Set up your API keys

```bash
cp .env.example .env
```

Edit `.env`:

```
ALPHA_VANTAGE_API_KEY=your_key   # https://www.alphavantage.co/support/#api-key
FRED_API_KEY=your_key            # https://fred.stlouisfed.org/docs/api/api_key.html
SEC_USER_AGENT=Your Name your@email.com
```

Both keys are free and approved instantly.

### 3. Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector python server.py
```

Open `localhost:6274`, add your env vars under "Environment Variables", and hit Connect. You'll see all six tools and can call them interactively.

### 4. Connect to Claude Desktop

Open Claude Desktop → Settings → Developer → Edit Config and add:

```json
{
  "mcpServers": {
    "financial": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/financial-mcp-server/server.py"],
      "env": {
        "ALPHA_VANTAGE_API_KEY": "your_key",
        "FRED_API_KEY": "your_key",
        "SEC_USER_AGENT": "Your Name your@email.com"
      }
    }
  }
}
```

> **Important:** Use the full absolute path to your venv's Python, not just `python`. Claude Desktop launches with a minimal PATH and will fail to find it otherwise.

Fully quit and reopen Claude Desktop. The tools will be available automatically in any new chat.

---

## Example Queries

Once connected, try these in Claude Desktop:

```
Search SEC EDGAR for Microsoft and get their last 3 10-K filings.
```

```
What is the current 10-year Treasury yield and how has it trended over the last 12 months?
```

```
Get NVIDIA's stock fundamentals and compare their P/E ratio against the current Fed funds rate.
```

```
Pull Apple's most recent 10-Q filing and their current stock price. Summarize in one paragraph.
```

---

## Project Structure

```
financial-mcp-server/
├── server.py          # FastMCP server — registers all tools
├── tools/
│   ├── edgar.py       # SEC EDGAR: company search + filings
│   ├── fred.py        # FRED: series search + observations
│   └── market.py      # Alpha Vantage: quotes + fundamentals
├── utils/
│   └── http.py        # Shared async HTTP client + error handling
├── .env.example       # API key template
└── requirements.txt
```

---

## Design Decisions

**Why MCP?** MCP is a open standard now adopted by Anthropic, OpenAI, Google DeepMind, Microsoft, and Salesforce. Building to the protocol — rather than a proprietary plugin API — means this server works with any compliant client today and every one that ships tomorrow.

**Why these three APIs?** They form a complete picture for fundamental financial analysis: corporate disclosures (EDGAR), macro context (FRED), and market pricing (Alpha Vantage). All three have free tiers with no credit card required, so the server works out of the box for any developer.

**Why async throughout?** Financial queries often need to be chained — search for a CIK, then fetch filings, then pull macro context in parallel. Async handlers let Claude pipeline tool calls efficiently without blocking.

---

## Requirements

- Python 3.11+
- `mcp[cli]`, `httpx`, `pydantic`, `python-dotenv`
- Free API keys for FRED and Alpha Vantage
- Claude Desktop (or any MCP-compatible client)

---

## License

MIT — use it, fork it, extend it.

---

*Built as part of a portfolio project exploring agentic AI infrastructure. Contributions and issues welcome.*