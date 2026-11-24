import numpy as np

from src.features import FEATURE_COLS, HORIZON, build_dataset, make_row
from src.preprocess import add_indicators, clean
from tests.conftest import synthetic_df


def test_make_row_has_all_features():
    row = make_row(np.linspace(100, 200, 60))
    assert set(row) == set(FEATURE_COLS)


def test_build_dataset_shapes():
    closes = np.linspace(100, 200, 80)
    X, y = build_dataset(closes)
    assert len(X) == len(y) == 80 - 30
    assert list(X.columns) == FEATURE_COLS


def test_preprocess_adds_indicators():
    df = add_indicators(clean(synthetic_df(60)))
    assert {"ma7", "ma30", "vol7", "target_next_close"} <= set(df.columns)
    assert HORIZON == 7
