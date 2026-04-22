"""Reparto de numResults entre varias consultas Exa (directorio)."""

from __future__ import annotations

from mle.nodes.exa_webset_node import MAX_EXA_RESULTS_PER_CALL, MIN_RESULTS_PER_QUERY, _fair_num_results_for_query_slot


def test_fair_split_single_query_uses_full_budget() -> None:
    assert _fair_num_results_for_query_slot(50, 0, 1) == 50


def test_fair_split_two_queries_sums_to_at_least_budget_when_each_above_min() -> None:
    a = _fair_num_results_for_query_slot(40, 0, 2)
    b = _fair_num_results_for_query_slot(40, 1, 2)
    assert a + b >= 40
    assert a == 20
    assert b == 20


def test_fair_split_three_queries_40() -> None:
    vals = [_fair_num_results_for_query_slot(40, i, 3) for i in range(3)]
    assert sum(vals) >= 40
    assert vals == [14, 13, 13]


def test_capped_at_api_max() -> None:
    v = _fair_num_results_for_query_slot(500, 0, 1)
    assert v == MAX_EXA_RESULTS_PER_CALL


def test_small_budget_raises_to_min_per_slot() -> None:
    v0 = _fair_num_results_for_query_slot(5, 0, 2)
    v1 = _fair_num_results_for_query_slot(5, 1, 2)
    assert v0 >= MIN_RESULTS_PER_QUERY
    assert v1 >= MIN_RESULTS_PER_QUERY
