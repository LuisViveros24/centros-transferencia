"""
Tests del endpoint /api/mapa (solo admin) y del helper de agregación
_colonias_para_mapa (origen dominante + total por colonia).
"""
import base64, pytest
from unittest.mock import patch, MagicMock
import app as app_module

AUTH_ADMIN   = {'Authorization': 'Basic ' + base64.b64encode(b'admin_test:clave_admin').decode()}
AUTH_CAPTURA = {'Authorization': 'Basic ' + base64.b64encode(b'usuario_test:clave_test').decode()}


def fake_db(fetchall_value=None):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = fetchall_value or []
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


class TestMapaAcceso:
    def test_captura_no_ve_mapa(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/mapa', headers=AUTH_CAPTURA).status_code == 403

    def test_admin_ve_mapa(self, client):
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/mapa?desde=2026-07-01&hasta=2026-07-31', headers=AUTH_ADMIN)
        assert r.status_code == 200
        assert isinstance(r.get_json()['colonias'], list)


class TestMapaSQL:
    def test_join_y_filtros(self, client):
        conn = fake_db()
        cur = conn.cursor.return_value
        with patch('app.get_db', return_value=conn):
            client.get('/api/mapa?desde=2026-07-01&hasta=2026-07-31', headers=AUTH_ADMIN)
        sql = cur.execute.call_args_list[0].args[0]
        assert 'JOIN colonias_geo' in sql, "Debe cruzar con el caché de coordenadas"
        assert "cg.estado='ok'" in sql, "Solo colonias geocodificadas con éxito"
        assert "r.tipo='ENTRADA'" in sql, "Solo entradas"
        assert 'fecha BETWEEN %s AND %s' in sql, "Debe respetar el periodo"

    def test_filtro_pga(self, client):
        conn = fake_db()
        cur = conn.cursor.return_value
        with patch('app.get_db', return_value=conn):
            client.get('/api/mapa?desde=2026-07-01&hasta=2026-07-31&pga=LEY%20SAULO', headers=AUTH_ADMIN)
        sql, params = cur.execute.call_args_list[0].args
        assert 'AND r.pga = %s' in sql
        assert 'LEY SAULO' in params

    def test_sin_pga_no_filtra(self, client):
        conn = fake_db()
        cur = conn.cursor.return_value
        with patch('app.get_db', return_value=conn):
            client.get('/api/mapa?desde=2026-07-01&hasta=2026-07-31', headers=AUTH_ADMIN)
        assert 'AND r.pga = %s' not in cur.execute.call_args_list[0].args[0]

    def test_fecha_invalida_400(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/mapa?desde=xx&hasta=2026-07-31', headers=AUTH_ADMIN).status_code == 400

    def test_rango_invertido_400(self, client):
        with patch('app.get_db', return_value=fake_db()):
            assert client.get('/api/mapa?desde=2026-07-31&hasta=2026-07-01', headers=AUTH_ADMIN).status_code == 400


class TestColoniasParaMapa:
    def test_agrupa_total_y_origen_dominante(self):
        rows = [
            {'norm': 'centro', 'colonia': 'Centro', 'lat': 25.54, 'lng': -103.41, 'origen': 'NEGOCIO', 'c': 3},
            {'norm': 'centro', 'colonia': 'Centro', 'lat': 25.54, 'lng': -103.41, 'origen': 'CEA', 'c': 5},
            {'norm': 'moderna', 'colonia': 'Moderna', 'lat': 25.55, 'lng': -103.42, 'origen': 'CONTRATISTAS', 'c': 2},
        ]
        out = app_module._colonias_para_mapa(rows)
        by = {c['colonia']: c for c in out}
        # Centro: total 8, dominante CEA (5 > 3)
        assert by['Centro']['count'] == 8
        assert by['Centro']['origen'] == 'CEA'
        assert by['Centro']['lat'] == 25.54 and by['Centro']['lng'] == -103.41
        # Moderna: total 2, dominante CONTRATISTAS
        assert by['Moderna']['count'] == 2
        assert by['Moderna']['origen'] == 'CONTRATISTAS'

    def test_orden_desc_por_conteo(self):
        rows = [
            {'norm': 'a', 'colonia': 'A', 'lat': 1, 'lng': 1, 'origen': 'NEGOCIO', 'c': 1},
            {'norm': 'b', 'colonia': 'B', 'lat': 2, 'lng': 2, 'origen': 'NEGOCIO', 'c': 9},
        ]
        out = app_module._colonias_para_mapa(rows)
        assert [c['colonia'] for c in out] == ['B', 'A']

    def test_vacio(self):
        assert app_module._colonias_para_mapa([]) == []
