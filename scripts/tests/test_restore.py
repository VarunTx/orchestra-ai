"""Restore safety tests use a fake Docker CLI; no databases are contacted."""
import gzip
import os
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).resolve().parents[1] / 'restore.sh'


def test_restore_refuses_existing_database_without_in_place(tmp_path):
    backup = tmp_path / 'orchestra-fixture.sql.gz'
    with gzip.open(backup, 'wb') as archive:
        archive.write(b'DROP TABLE important;')
    calls = tmp_path / 'calls'
    docker = tmp_path / 'docker'
    docker.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\ncase "$*" in\n  *pg_database*) echo 1;;\nesac\n')
    docker.chmod(0o755)
    result = subprocess.run(['bash', str(SCRIPT), str(backup), '--database', 'orchestra'],
                            env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH'],
                                 'CALLS': str(calls)}, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'already exists' in result.stderr
    assert '-d orchestra ' not in calls.read_text()


def test_restore_rejects_sql_in_database_name(tmp_path):
    backup = tmp_path / 'orchestra-fixture.sql.gz'
    with gzip.open(backup, 'wb') as archive:
        archive.write(b'SELECT 1;')
    docker = tmp_path / 'docker'
    docker.write_text('#!/bin/sh\nexit 99\n')
    docker.chmod(0o755)
    result = subprocess.run(['bash', str(SCRIPT), str(backup), '--database', 'bad";name'],
                            env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH']},
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'invalid database name' in result.stderr


def test_restore_creates_new_database_and_restores(tmp_path):
    backup = tmp_path / 'orchestra-fixture.sql.gz'
    with gzip.open(backup, 'wb') as archive:
        archive.write(b'SELECT 1;')
    calls = tmp_path / 'calls'
    docker = tmp_path / 'docker'
    docker.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\ncase "$*" in\n  *pg_database*) exit 0;;\n  *"-d orchestra_restore -v"*) cat >/dev/null;;\nesac\n')
    docker.chmod(0o755)
    result = subprocess.run(['bash', str(SCRIPT), str(backup)],
                            env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH'],
                                 'CALLS': str(calls)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'CREATE DATABASE "orchestra_restore"' in calls.read_text()
    assert '-d orchestra_restore -v ON_ERROR_STOP=1' in calls.read_text()


def test_restore_stops_when_database_lookup_fails(tmp_path):
    backup = tmp_path / 'orchestra-fixture.sql.gz'
    with gzip.open(backup, 'wb') as archive:
        archive.write(b'SELECT 1;')
    calls = tmp_path / 'calls'
    docker = tmp_path / 'docker'
    docker.write_text('#!/bin/sh\necho "$*" >> "$CALLS"\nexit 1\n')
    docker.chmod(0o755)
    result = subprocess.run(['bash', str(SCRIPT), str(backup)],
                            env={**os.environ, 'PATH': f'{tmp_path}:' + os.environ['PATH'],
                                 'CALLS': str(calls)}, capture_output=True, text=True)
    assert result.returncode != 0
    assert len(calls.read_text().splitlines()) == 1
