"""Fixture modules loaded via `pytest_plugins` in the root conftest.

Splitting fixtures by concern (db, integrations, app, clients) keeps the
conftest to environment setup and collection hooks. Fixture names are global
either way — tests request them exactly as before.
"""
