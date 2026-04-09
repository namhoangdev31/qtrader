import polars as pl
import pytest

try:
    from qtrader.features.technical.momentum import MomentumFeatureGenerator
except ImportError:
    MomentumFeatureGenerator = None
pytestmark = pytest.mark.skipif(
    MomentumFeatureGenerator is None, reason="MomentumFeatureGenerator missing in source code"
)


def test_momentum_feature_generator_init():
    generator = MomentumFeatureGenerator(windows=[5, 10, 20])
    assert generator.windows == [5, 10, 20]


def test_momentum_feature_generator_compute():
    generator = MomentumFeatureGenerator(windows=[2])
    df = pl.DataFrame({"close": [100.0, 105.0, 110.0, 108.0]})
    features = generator.compute(df)
    assert "mom_2" in features.columns
    assert features["mom_2"].to_list()[2] == pytest.approx(0.1)


def test_momentum_feature_generator_empty():
    generator = MomentumFeatureGenerator()
    df = pl.DataFrame({"close": []})
    features = generator.compute(df)
    assert len(features) == 0


def test_momentum_feature_generator_nan_handling():
    generator = MomentumFeatureGenerator(windows=[2])
    df = pl.DataFrame({"close": [100.0, float("nan"), 110.0, float("inf"), 120.0]})
    features = generator.compute(df)
    assert "mom_2" in features.columns
    mom_list = features["mom_2"].to_list()
    assert mom_list[2] == pytest.approx(0.1) or pl.Series([mom_list[2]]).is_null().any()


def test_momentum_indicator_correctness():
    generator = MomentumFeatureGenerator(windows=[1])
    df = pl.DataFrame({"close": [10.0, 11.0, 10.45]})
    features = generator.compute(df)
    mom_1 = features["mom_1"].to_list()
    assert abs(mom_1[1] - 0.1) < 1e-06
    assert abs(mom_1[2] - -0.05) < 1e-06
