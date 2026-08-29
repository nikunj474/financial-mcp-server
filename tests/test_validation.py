"""Input contracts. These models are the only thing standing between a
hallucinated tool call and a malformed upstream request, so they are tested
first."""
import pytest
from pydantic import ValidationError

from tools.edgar import CompanySearchInput, FilingsInput
from tools.fred import FredSearchInput, FredSeriesInput
from tools.market import TickerInput


def test_company_search_trims_whitespace():
    assert CompanySearchInput(query="  Apple  ").query == "Apple"


def test_company_search_rejects_empty_query():
    with pytest.raises(ValidationError):
        CompanySearchInput(query="")


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (CompanySearchInput, {"query": "Apple", "sneaky": 1}),
        (FilingsInput, {"cik": "0000320193", "sneaky": 1}),
        (TickerInput, {"ticker": "AAPL", "sneaky": 1}),
    ],
)
def test_models_forbid_unknown_fields(model, kwargs):
    """extra='forbid' is what stops a model from inventing parameters."""
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_filings_limit_is_bounded():
    assert FilingsInput(cik="0000320193", limit=40).limit == 40
    with pytest.raises(ValidationError):
        FilingsInput(cik="0000320193", limit=0)
    with pytest.raises(ValidationError):
        FilingsInput(cik="0000320193", limit=41)


def test_filings_defaults():
    params = FilingsInput(cik="320193")
    assert params.limit == 10
    assert params.form_type is None


def test_fred_models_accept_minimal_input():
    assert FredSeriesInput(series_id="FEDFUNDS").series_id == "FEDFUNDS"
    assert FredSearchInput(query="federal funds rate").query == "federal funds rate"
