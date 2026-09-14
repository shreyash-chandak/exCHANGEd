import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: marks tests that call real models or the live tau2 environment"
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("CHANGE_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="set CHANGE_LIVE=1 to run live tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
