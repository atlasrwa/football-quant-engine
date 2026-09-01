"""Pytest configuration for the Asymmetric Matchup Engine test suite.

Project imports resolve via ``src.*`` because ``pythonpath = ["."]`` is set in
``pyproject.toml`` under ``[tool.pytest.ini_options]``; no path manipulation is
required here. Shared fixtures and custom Hypothesis strategies for these tests
are added in later tasks (see task 12.1).
"""

from __future__ import annotations
