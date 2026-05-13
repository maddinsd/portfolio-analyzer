from dataclasses import dataclass
import pandas as pd
import yfinance as yf

INFO_FIELDS = (
    "currentPrice",
    "marketCap",
    "trailingPE",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "sector",
)


@dataclass
class TickerData:
    ticker: str
    history: pd.DataFrame
    info: dict


def fetch_ticker(ticker: str) -> TickerData:
    t = yf.Ticker(ticker)
    history = t.history(period="6mo", interval="1d", auto_adjust=True)
    if history.empty:
        raise ValueError(f"No price history returned for ticker {ticker!r} — is it valid?")

    raw_info = t.info or {}
    if not raw_info.get("currentPrice") and not raw_info.get("regularMarketPrice"):
        raise ValueError(f"No info fields returned for ticker {ticker!r} — is it valid?")

    info = {field: raw_info.get(field) for field in INFO_FIELDS}
    return TickerData(ticker=ticker, history=history, info=info)


def fetch_all(tickers: list[str]) -> list[TickerData]:
    return [fetch_ticker(t) for t in tickers]
