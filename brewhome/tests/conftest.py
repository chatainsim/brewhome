import os
import sys

# Ensure brewhome/ is importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import db as db_module


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """
    Flask test app backed by a fresh, isolated SQLite DB for each test.
    monkeypatch restores the real DB paths automatically after each test.
    """
    monkeypatch.setattr(db_module, 'DB_PATH',          str(tmp_path / 'test.db'))
    monkeypatch.setattr(db_module, 'READINGS_DB_PATH', str(tmp_path / 'test_readings.db'))

    from app import app as flask_app
    flask_app.config['TESTING'] = True

    with flask_app.app_context():
        db_module.init_db()
        db_module.init_readings_db()
        db_module.migrate_db()

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
