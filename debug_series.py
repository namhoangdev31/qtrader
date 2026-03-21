import polars as pl

# Test creating a series the way we're trying to do it
try:
    s = pl.Series([0.0, 0.0, 0.0], name="test", dtype=pl.Float64)
    print("Success:", s)
except Exception as e:
    print("Error:", e)
    print("Type of error:", type(e))

# Test alternative ways
try:
    s = pl.Series(values=[0.0, 0.0, 0.0], name="test", dtype=pl.Float64)
    print("Success with keywords:", s)
except Exception as e:
    print("Error with keywords:", e)

try:
    s = pl.Series([0.0, 0.0, 0.0]).alias("test")
    print("Success with alias:", s)
except Exception as e:
    print("Error with alias:", e)