import os

os.environ['CONTROL_PLANE_TOKEN'] = 'test-control-plane-token-00000000000'
os.environ['ENABLE_GEMINI'] = 'false'
# Isolated application database; never the live one.
os.environ.setdefault('TEST_DATABASE_NAME', 'orchestra_test')
os.environ['DATABASE_NAME'] = os.environ['TEST_DATABASE_NAME']
os.environ.setdefault('DATABASE_HOST', 'localhost')
os.environ.setdefault('MONITOR_ENABLED', 'false')

# Override the database inside an explicit DSN as well as DATABASE_NAME. Otherwise
# a developer's DATABASE_URL could make truncating fixtures touch their app data.
from psycopg.conninfo import make_conninfo
from app.settings import Settings

os.environ['DATABASE_URL'] = make_conninfo(
    Settings().database_url, dbname=os.environ['TEST_DATABASE_NAME'],
)


def database_reachable() -> bool:
    """Create the isolated test database when PostgreSQL is reachable."""
    import psycopg
    from app.db import Database
    from app.settings import Settings
    try:
        settings = Settings()
        Database(settings).ensure_database()
        with psycopg.connect(settings.database_url, connect_timeout=3):
            return True
    except Exception:
        return False


DB_AVAILABLE = database_reachable()

requires_db = __import__('pytest').mark.skipif(
    not DB_AVAILABLE,
    reason='application database unavailable: set DATABASE_HOST/DATABASE_PASSWORD '
           '(run tests inside the api container or point DATABASE_URL at PostgreSQL)',
)
