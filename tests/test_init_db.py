"""
Tests para init_db() — verifica que el esquema local (desarrollo)
incluya las columnas nombre y calle en la tabla registros.

nombre ya se usaba sin estar en este CREATE TABLE (brecha preexistente,
detectada durante la revisión del spec de 2026-07-15); calle es nueva.
"""
import os, sys
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('AUTH_USER', 'usuario_test')
os.environ.setdefault('AUTH_PASS', 'clave_test')

if 'app' in sys.modules:
    del sys.modules['app']

import app as app_module


def fake_db():
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


class TestInitDbSchema:
    def test_create_table_incluye_nombre_y_calle(self):
        conn, cur = fake_db()
        with patch('app.get_db', return_value=conn):
            app_module.init_db()

        create_calls = [
            c.args[0] for c in cur.execute.call_args_list
            if 'CREATE TABLE IF NOT EXISTS registros' in c.args[0]
        ]
        assert create_calls, "No se ejecutó el CREATE TABLE de registros"
        sql = create_calls[0]
        assert 'nombre' in sql, "Falta columna nombre en el CREATE TABLE (brecha preexistente sin corregir)"
        assert 'calle' in sql, "Falta columna calle en el CREATE TABLE"
