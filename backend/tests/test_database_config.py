from psycopg.conninfo import conninfo_to_dict

from app.db import Database
from app.settings import Settings


def test_explicit_database_url_controls_connections_and_creation():
    settings = Settings(_env_file=None, database_url=(
        'postgresql://remote_user:synthetic@db.example:5433/selected?sslmode=require'
    ))
    db = Database(settings)
    connection = conninfo_to_dict(db._dsn())
    assert connection['host'] == 'db.example'
    assert connection['dbname'] == 'selected'
    assert connection['sslmode'] == 'require'
    assert settings.database_name == 'selected'
    admin = conninfo_to_dict(db._dsn(settings.database_admin_name))
    assert admin == {**connection, 'dbname': 'postgres'}


def test_individual_database_fields_remain_supported():
    settings = Settings(_env_file=None, database_url='', database_host='db.example',
                        database_name='a database', database_user='user@name',
                        database_password='p@ss:/word')
    connection = conninfo_to_dict(Database(settings)._dsn())
    assert connection['dbname'] == 'a database'
    assert connection['user'] == 'user@name'
    assert connection['password'] == 'p@ss:/word'
