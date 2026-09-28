import pandas as pd

from stp.data.audit import compare_columns
from stp.data.build_tables import normalize_flaky_name


def test_compare_columns_counts_matches_mismatches_and_one_sided_rows():
    left = pd.DataFrame({"project": ["a", "a", "b"], "k": [1, 2, 3], "n": [5, 6, 7]})
    right = pd.DataFrame({"project": ["a", "a", "b"], "k": [1, 2, 4], "n_r": [5, 0, 7]})
    summ, mism = compare_columns(left, right, ["project", "k"], [("n", "n_r")])
    assert summ.loc["a", "matched_rows"] == 2
    assert summ.loc["a", "all_equal"] == 1
    assert summ.loc["a", "match_rate"] == 0.5
    assert summ.loc["b", "left_only"] == 1 and summ.loc["b", "right_only"] == 1
    assert list(mism.k) == [2]


def test_compare_columns_treats_both_null_as_equal():
    left = pd.DataFrame({"project": ["a"], "k": [1], "n": [None]})
    right = pd.DataFrame({"project": ["a"], "k": [1], "n_r": [None]})
    summ, mism = compare_columns(left, right, ["project", "k"], [("n", "n_r")])
    assert summ.loc["a", "match_rate"] == 1.0 and mism.empty


def test_normalize_flaky_name():
    assert normalize_flaky_name("FooTest#testBar") == ("FooTest", "testBar")
    assert normalize_flaky_name("[qfile_1]") == (None, "[qfile_1]")
    assert normalize_flaky_name("a.b.FooTest") == ("a.b.FooTest", None)
