from datetime import date, timedelta

from bot.insider import InsiderTx, _to_float, cluster_buy_signal

TODAY = date(2026, 8, 21)


def tx(person, action="buy", days_ago=5, lag=2, value=100_000.0, title="Director"):
    traded = TODAY - timedelta(days=days_ago)
    return InsiderTx(
        symbol="ACME",
        person=person,
        title=title,
        action=action,
        value=value,
        shares=1000.0,
        traded_on=traded,
        filed_on=traded + timedelta(days=lag),
    )


def signal(transactions, **kwargs):
    return cluster_buy_signal(transactions, today=TODAY, **kwargs)


def test_cluster_of_three_buyers_fires():
    result = signal([tx("Alice"), tx("Bob"), tx("Carol")])
    assert result.action == "buy"
    assert result.buyers == 3
    assert result.net_value == 300_000.0
    assert "Alice (Director)" in result.people


def test_two_buyers_are_not_a_cluster():
    result = signal([tx("Alice"), tx("Bob")])
    assert result.action == "hold"
    assert "2 Kaeufer" in result.reason


def test_same_person_buying_repeatedly_is_one_buyer():
    result = signal([tx("Alice", days_ago=3), tx("Alice", days_ago=7), tx("Bob")])
    assert result.buyers == 2
    assert result.action == "hold"


def test_stale_filings_are_dropped():
    # Kongress-Report, erst 40 Tage nach dem Trade veroeffentlicht -> eingepreist
    late = [tx(p, lag=40) for p in ("Alice", "Bob", "Carol")]
    result = signal(late, max_filing_lag_days=21)
    assert result.action == "hold"
    assert "zu spaet gemeldet" in result.reason


def test_trades_outside_lookback_are_ignored():
    old = [tx(p, days_ago=90) for p in ("Alice", "Bob", "Carol")]
    assert signal(old, lookback_days=30).action == "hold"


def test_sellers_outweighing_buyers_block_the_signal():
    txs = [tx(p) for p in ("Alice", "Bob", "Carol")]
    txs += [tx(p, action="sell") for p in ("Dave", "Erin", "Frank")]
    result = signal(txs)
    assert result.action == "hold"
    assert result.sellers == 3


def test_person_who_also_sold_does_not_count_as_buyer():
    txs = [tx("Alice"), tx("Bob"), tx("Carol"), tx("Carol", action="sell")]
    result = signal(txs)
    assert result.buyers == 2
    assert result.action == "hold"


def test_negative_net_volume_blocks_the_signal():
    txs = [tx(p, value=10_000.0) for p in ("Alice", "Bob", "Carol")]
    txs.append(tx("Dave", action="sell", value=500_000.0))
    result = signal(txs)
    assert result.action == "hold"
    assert result.net_value < 0


def test_officer_buys_score_higher_than_large_holders():
    officers = signal([tx(p, title="CFO") for p in ("Alice", "Bob", "Carol")])
    holders = signal([tx(p, title="10% Owner") for p in ("Alice", "Bob", "Carol")])
    assert officers.score > holders.score


def test_empty_input_is_a_hold():
    result = cluster_buy_signal([], today=TODAY)
    assert result.action == "hold"
    assert result.symbol == "?"


def test_to_float_parses_congress_ranges_and_currency():
    assert _to_float("$1,001 - $15,000") == 8000.5
    assert _to_float("$250,000") == 250_000.0
    assert _to_float(None) == 0.0
