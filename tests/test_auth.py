"""
Tests de HTTP Basic Auth — no requieren base de datos real.
Se parchea DATABASE_URL y AUTH_USER/AUTH_PASS antes de importar app.
"""
import os, sys, pytest

# Inyectar variables de entorno ANTES de importar app (el módulo las lee al cargar)
os.environ['DATABASE_URL'] = 'postgresql://fake:fake@localhost/fake'
os.environ['AUTH_USER'] = 'usuario_test'
os.environ['AUTH_PASS'] = 'clave_test'

# Forzar reimport limpio si el módulo ya estaba cargado
if 'app' in sys.modules:
    del sys.modules['app']

import app as app_module
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c

def fake_db():
    """Conexión psycopg2 completamente mockeada."""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = []
    cur.fetchone.return_value = {'c': 0, 'v': 0}
    conn.cursor.return_value = cur
    return conn


class TestAuth:
    def test_sin_credenciales_devuelve_401(self, client):
        r = client.get('/')
        assert r.status_code == 401

    def test_credenciales_incorrectas_devuelven_401(self, client):
        r = client.get('/', headers={
            'Authorization': 'Basic dXN1YXJpb193cm9uZzpjbGF2ZV93cm9uZw=='
            # usuario_wrong:clave_wrong en base64
        })
        assert r.status_code == 401

    def test_credenciales_correctas_pasan(self, client):
        import base64
        token = base64.b64encode(b'usuario_test:clave_test').decode()
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/', headers={'Authorization': f'Basic {token}'})
        # 200 (HTML) o cualquier código que no sea 401 confirma que el auth pasó
        assert r.status_code != 401

    def test_delete_sin_auth_devuelve_401(self, client):
        r = client.delete('/api/registros/1')
        assert r.status_code == 401

    def test_api_registros_sin_auth_devuelve_401(self, client):
        r = client.get('/api/registros')
        assert r.status_code == 401

    def test_dashboard_sin_auth_devuelve_401(self, client):
        r = client.get('/api/dashboard')
        assert r.status_code == 401

    def test_export_sin_auth_devuelve_401(self, client):
        r = client.get('/api/export/excel')
        assert r.status_code == 401

    def test_post_registros_sin_auth_devuelve_401(self, client):
        r = client.post('/api/registros', json={})
        assert r.status_code == 401
