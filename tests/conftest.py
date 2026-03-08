"""
Pytest configuration for Siftout's test suite.
"""

import logging

import pytest

# Silence siftout's own logger during tests unless -v is passed
@pytest.fixture(autouse=True)
def _quiet_logger(caplog):
    with caplog.at_level(logging.WARNING, logger="siftout"):
        yield