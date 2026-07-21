"""
Tests de roles: el usuario de captura (AUTH_USER) solo puede registrar
y autocompletar; el admin (ADMIN_USER) tiene acceso total. Endpoints de
análisis (historial, dashboard, export, delete) devuelven 403 a captura.
"""
import base64, pytest
from unittest.mock import patch, MagicMock
import app as app_module

AUTH_CAPTURA = {'Authorization': 'Basic ' + base64.b64encode(b'usuario_test:clave_test').decode()}
AUTH_ADMIN   = {'Authorization': 'Basic ' + base64.b64encode(b'admin_test:clave_admin').decode()}


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
    return conn


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


ENTRADA_OK = {'tipo': 'ENTRADA', 'fecha': '2026-07-19', 'pga': 'ESTERITO',
              'origen': 'NEGOCIO', 'placa': 'ABC-123-D', 'm3': 2.5}


class TestCapturaRestringido:
    def test_captura_no_ve_historial(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/registros', headers=AUTH_CAPTURA).status_code == 403

    def test_captura_no_ve_dashboard(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/dashboard', headers=AUTH_CAPTURA).status_code == 403

    def test_captura_no_exporta(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/export/excel', headers=AUTH_CAPTURA).status_code == 403

    def test_captura_no_elimina(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.delete('/api/registros/1', headers=AUTH_CAPTURA).status_code == 403


class TestCapturaPermitido:
    def test_captura_puede_registrar(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'valor': '1'})):
            r = client.post('/api/registros', json=ENTRADA_OK, headers=AUTH_CAPTURA)
        assert r.status_code == 201

    def test_captura_puede_autocompletar(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/registros/buscar-placa?q=ABC123', headers=AUTH_CAPTURA).status_code == 200

    def test_captura_puede_ver_badges(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'c': 5})):
            r = client.get('/api/badges?fecha=2026-07-19', headers=AUTH_CAPTURA)
        assert r.status_code == 200
        data = r.get_json()
        assert 'ent' in data and 'sal' in data

    def test_captura_puede_ver_index(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/', headers=AUTH_CAPTURA).status_code != 401

    def test_index_no_se_cachea(self, client):
        """El HTML no debe quedar cacheado, para que un deploy nuevo llegue
        de inmediato a los operadores (evita frontend viejo + backend nuevo)."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/', headers=AUTH_CAPTURA)
        assert 'no-store' in r.headers.get('Cache-Control', '')


class TestLogout:
    def test_logout_responde_401_con_credenciales_validas(self, client):
        """El logout debe responder 401 aunque lleguen credenciales válidas,
        para invalidar la sesión Basic Auth cacheada."""
        r = client.get('/logout', headers=AUTH_ADMIN)
        assert r.status_code == 401
        assert 'Basic realm="CT App"' in r.headers.get('WWW-Authenticate', '')

    def test_logout_sin_credenciales_tambien_401(self, client):
        assert client.get('/logout').status_code == 401


class TestAdmin:
    def test_admin_ve_dashboard(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'c': 0, 'v': 0})):
            assert client.get('/api/dashboard', headers=AUTH_ADMIN).status_code == 200

    def test_admin_ve_historial(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/registros', headers=AUTH_ADMIN).status_code == 200

    def test_admin_puede_registrar(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'valor': '1'})):
            assert client.post('/api/registros', json=ENTRADA_OK, headers=AUTH_ADMIN).status_code == 201


class TestWhoami:
    def test_whoami_captura(self, client):
        r = client.get('/api/whoami', headers=AUTH_CAPTURA)
        assert r.status_code == 200
        assert r.get_json()['rol'] == 'captura'

    def test_whoami_admin(self, client):
        r = client.get('/api/whoami', headers=AUTH_ADMIN)
        assert r.status_code == 200
        assert r.get_json()['rol'] == 'admin'

    def test_whoami_sin_credenciales_401(self, client):
        assert client.get('/api/whoami').status_code == 401

    def test_whoami_credenciales_invalidas_401(self, client):
        malas = {'Authorization': 'Basic ' + base64.b64encode(b'x:y').decode()}
        assert client.get('/api/whoami', headers=malas).status_code == 401


class TestSinAdminConfigurado:
    """Sin ADMIN_USER/ADMIN_PASS, el usuario actual conserva acceso total
    (migración segura: el deploy no rompe nada antes de configurar Render)."""

    def test_auth_user_es_admin_si_no_hay_admin(self, client):
        with patch.object(app_module, 'ADMIN_USER', None), \
             patch.object(app_module, 'ADMIN_PASS', None):
            r = client.get('/api/whoami', headers=AUTH_CAPTURA)
            assert r.get_json()['rol'] == 'admin'
            with patch('app.get_db', return_value=fake_db(fetchone_value={'c': 0, 'v': 0})):
                assert client.get('/api/dashboard', headers=AUTH_CAPTURA).status_code == 200
