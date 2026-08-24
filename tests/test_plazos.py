"""
Tests del módulo de plazos: /api/plazos (listado) y /api/domicilios/<id>/cumplir
(confirmar cumplimiento). Solo admin puede verlos/actuar; el dashboard expone
el conteo de vencidos.
"""
import base64
import pytest
from unittest.mock import patch, MagicMock
import app as app_module

VIEWER = ('jefe_test', 'clave_jefe')


def _auth(u, p):
    return {'Authorization': 'Basic ' + base64.b64encode(f'{u}:{p}'.encode('utf-8')).decode()}


def fake_db(fetchone_value=None, fetchall_value=None, rowcount=1):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_value if fetchone_value is not None else {'c': 0}
    cur.fetchall.return_value = fetchall_value or []
    cur.rowcount = rowcount
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


class TestPlazosListado:
    def test_admin_ve_plazos(self, client):
        with patch('app.get_db', return_value=fake_db(fetchall_value=[])):
            r = client.get('/api/plazos', headers=_auth('admin_test', 'clave_admin'))
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_plazos_clasifica_estado(self, client):
        filas = [
            {'id': 1, 'folio': 'DOM-0001', 'cumplido': False, 'vencido': True,
             'plazo_horas': 24, 'limite': None, 'direccion': '', 'equipo': '',
             'problematica': '', 'accion': '', 'fecha': '2026-08-01', 'uso': '',
             'nombre_comercio': '', 'estado': '', 'obs': '', 'folio_acta': '',
             'cumplido_en': None, 'cumplido_obs': None, 'cumplido_por': None},
            {'id': 2, 'folio': 'DOM-0002', 'cumplido': True, 'vencido': False,
             'plazo_horas': 24, 'limite': None, 'direccion': '', 'equipo': '',
             'problematica': '', 'accion': '', 'fecha': '2026-08-01', 'uso': '',
             'nombre_comercio': '', 'estado': '', 'obs': '', 'folio_acta': '',
             'cumplido_en': None, 'cumplido_obs': None, 'cumplido_por': None,
             'incumplimiento': False},
            {'id': 3, 'folio': 'DOM-0003', 'cumplido': True, 'vencido': True,
             'plazo_horas': 24, 'limite': None, 'direccion': '', 'equipo': '',
             'problematica': '', 'accion': '', 'fecha': '2026-08-01', 'uso': '',
             'nombre_comercio': '', 'estado': '', 'obs': '', 'folio_acta': '',
             'cumplido_en': None, 'cumplido_obs': None, 'cumplido_por': None,
             'incumplimiento': True},
        ]
        with patch('app.get_db', return_value=fake_db(fetchall_value=filas)):
            r = client.get('/api/plazos?estado=todos', headers=_auth('admin_test', 'clave_admin'))
        data = r.get_json()
        estados = {d['folio']: d['estado_plazo'] for d in data}
        assert estados['DOM-0001'] == 'vencido'
        assert estados['DOM-0002'] == 'cumplido'
        assert estados['DOM-0003'] == 'incumplimiento'

    def test_viewer_no_ve_plazos(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/plazos', headers=_auth(*VIEWER)).status_code == 403

    def test_captura_no_ve_plazos(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/plazos', headers=_auth('usuario_test', 'clave_test')).status_code == 403


class TestConfirmarCumplimiento:
    def test_admin_confirma(self, client):
        conn = fake_db(rowcount=1)
        cur = conn.cursor.return_value
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/domicilios/5/cumplir', json={'obs': 'Predio limpiado'},
                            headers=_auth('admin_test', 'clave_admin'))
        assert r.status_code == 200
        sql = ' '.join(c.args[0] for c in cur.execute.call_args_list)
        assert 'cumplido=TRUE' in sql and 'cumplido_obs' in sql

    def test_confirmar_id_inexistente_404(self, client):
        with patch('app.get_db', return_value=fake_db(rowcount=0)):
            r = client.post('/api/domicilios/999/cumplir', json={'obs': 'x'},
                            headers=_auth('admin_test', 'clave_admin'))
        assert r.status_code == 404

    def test_viewer_no_confirma(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.post('/api/domicilios/5/cumplir', json={'obs': 'x'},
                               headers=_auth(*VIEWER)).status_code == 403


class TestDashboardVencidos:
    def test_dashboard_incluye_vencidos(self, client):
        with patch('app.get_db', return_value=fake_db(fetchone_value={'c': 0, 'v': 0, 'p': 0})):
            r = client.get('/api/dashboard/domicilios', headers=_auth('admin_test', 'clave_admin'))
        assert r.status_code == 200
        data = r.get_json()
        assert 'vencidos' in data and 'por_vencer' in data
