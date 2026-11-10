"""numeric_summary: quartiles, whiskers and outliers."""

import pytest

from ingesta.utils import numeric_summary


def test_a_single_value_is_every_statistic() -> None:
    summary = numeric_summary([7])
    assert (summary.casos, summary.total, summary.min, summary.max) == (1, 7, 7, 7)
    assert (summary.q1, summary.mediana, summary.q3, summary.p90, summary.desviacion) == (7, 7, 7, 7, 0)


def test_the_values_dont_need_to_be_sorted() -> None:
    summary = numeric_summary([3, 1, 2])
    assert (summary.min, summary.mediana, summary.max) == (1, 2, 3)


def test_the_quartiles_are_inclusive() -> None:
    summary = numeric_summary([1, 2, 3, 4, 5])
    assert (summary.q1, summary.mediana, summary.q3) == pytest.approx((2, 3, 4))


def test_the_90th_percentile() -> None:
    assert numeric_summary(list(range(0, 101))).p90 == pytest.approx(90)


def test_the_mean_and_the_population_deviation() -> None:
    summary = numeric_summary([2, 4, 4, 4, 5, 5, 7, 9])
    assert (summary.media, summary.desviacion) == pytest.approx((5, 2))


def test_a_value_far_from_the_rest_is_an_outlier_outside_the_whiskers() -> None:
    summary = numeric_summary([1, 2, 3, 4, 100])
    assert (summary.atipicos, summary.bigote_inf, summary.bigote_sup) == (1, 1, 4)


def test_a_value_far_below_the_rest_is_an_outlier_too() -> None:
    summary = numeric_summary([-100, 2, 3, 4, 5])
    assert (summary.atipicos, summary.bigote_inf) == (1, 2)


def test_without_outliers_the_whiskers_are_the_ends() -> None:
    summary = numeric_summary([1, 2, 3])
    assert (summary.atipicos, summary.bigote_inf, summary.bigote_sup) == (0, 1, 3)
