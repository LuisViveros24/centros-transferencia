"""
Tests del rol de solo lectura (viewer/jefe) y del tablero.

El viewer ve el tablero y sus datos de solo lectura, pero queda excluido del
formulario de captura y de cualquier acción de escritura o borrado.
"""
import base64
import pytest
from unittest.mock import patch, MagicMock
import app as app_module

VIEWER = ('jefe_test', 'clave_jefe')


def _auth(u, p):
    return {'Authorization': 'Basic ' + base64.b64encode(f'{u}:{p}'.encode('utf-8')).decode()}


def fake_db(fetchone_value=None, fetchall_value=None):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_value if fetchone_value is not None else {'c': 0}
    cur.fetchall.return_value = fetchall_value or []
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _viewer_configurado():
    with patch.object(app_module, 'VIEWER_USER', VIEWER[0]), \
         patch.object(app_module, 'VIEWER_PASS', VIEWER[1]):
        yield


class TestViewerPermitido:
    def test_viewer_ve_tablero(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/tablero', headers=_auth(*VIEWER)).status_code == 200

    def test_viewer_ve_dashboard_domicilios(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'c': 0})):
            assert client.get('/api/dashboard/domicilios', headers=_auth(*VIEWER)).status_code == 200

    def test_viewer_ve_lista_del_tablero(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/tablero/domicilios', headers=_auth(*VIEWER)).status_code == 200


class TestViewerRestringido:
    def test_viewer_no_ve_capturador(self, client):
        assert client.get('/', headers=_auth(*VIEWER)).status_code == 403

    def test_viewer_no_puede_capturar_domicilio(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.post('/api/domicilios', json={}, headers=_auth(*VIEWER)).status_code == 403

    def test_viewer_no_puede_borrar(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.delete('/api/domicilios/1', headers=_auth(*VIEWER)).status_code == 403

    def test_viewer_no_ve_registros_captura(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/registros', headers=_auth(*VIEWER)).status_code == 403


class TestTableroOtrosRoles:
    def test_captura_no_ve_tablero(self, client):
        assert client.get('/tablero', headers=_auth('usuario_test', 'clave_test')).status_code == 403

    def test_admin_ve_tablero(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/tablero', headers=_auth('admin_test', 'clave_admin')).status_code == 200

    def test_sin_credenciales_tablero_401(self, client):
        assert client.get('/tablero').status_code == 401
