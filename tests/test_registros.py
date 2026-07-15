"""
Tests para POST /api/registros (incluye calle) y
GET /api/registros/buscar-placa (autocompletado incluye calle).
"""
import base64, pytest
from unittest.mock import patch, MagicMock
import app as app_module

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'usuario_test:clave_test').decode()}


def fake_db(fetchone_value=None, fetchall_value=None):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_value
    cur.fetchall.return_value = fetchall_value or []
    conn.cursor.return_value = cur
    return conn, cur


def _param_for_column(sql, params, column):
    """Ubica el valor pasado para `column` en un INSERT ...(col1,col2,...) VALUES (%s,%s,...)."""
    cols = [c.strip() for c in sql.split('(', 1)[1].split(')', 1)[0].split(',')]
    return params[cols.index(column)]


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


class TestCrearRegistroCalle:
    def test_post_registro_guarda_calle(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json={
                'tipo': 'ENTRADA', 'fecha': '2026-07-15', 'pga': 'ESTERITO',
                'origen': 'NEGOCIO', 'nombre': 'Juan Perez',
                'calle': 'Av. Reforma', 'colonia': 'Centro'
            }, headers=AUTH)
        assert r.status_code == 201

        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        assert insert_calls, "No se ejecutó el INSERT de registros"
        sql, params = insert_calls[0].args
        assert 'calle' in sql, "Falta la columna calle en el INSERT"
        assert _param_for_column(sql, params, 'calle') == 'Av. Reforma'

    def test_post_registro_sin_calle_guarda_cadena_vacia(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json={
                'tipo': 'ENTRADA', 'fecha': '2026-07-15', 'pga': 'ESTERITO', 'origen': 'NEGOCIO'
            }, headers=AUTH)
        assert r.status_code == 201
        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        sql, params = insert_calls[0].args
        assert _param_for_column(sql, params, 'calle') == ''
