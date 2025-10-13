
import pytest
try:
    from hypothesis import given, strategies as st
except Exception:
    pytest.skip("hypothesis not installed")

@pytest.mark.property
@pytest.mark.skip(reason="replace with real property invariants")
@given(st.text())
def test_placeholder_property(s):
    assert isinstance(s, str)
