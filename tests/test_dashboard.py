"""
Tests para el endpoint /api/dashboard con parámetros desde/hasta
y campos JSON renombrados.
"""
import base64, pytest
import app as app_module
from unittest.mock import patch, MagicMock

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'usuario_test:clave_test').decode()}


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


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


class TestDashboardNuevosParametros:
    def test_dashboard_retorna_ent_periodo_no_ent_hoy(self, client):
        """El campo JSON debe llamarse ent_periodo, no ent_hoy."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-04-01&hasta=2026-04-11', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert 'ent_periodo' in data, "Falta campo ent_periodo"
        assert 'sal_periodo' in data, "Falta campo sal_periodo"
        assert 'ent_hoy' not in data, "Campo antiguo ent_hoy no debe existir"
        assert 'sal_hoy' not in data, "Campo antiguo sal_hoy no debe existir"

    def test_dashboard_retorna_m3_periodo_no_m3_hoy(self, client):
        """Los campos de m³ deben usar sufijo _periodo."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-04-01&hasta=2026-04-11', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert 'm3_ent_periodo' in data, "Falta campo m3_ent_periodo"
        assert 'm3_sal_periodo' in data, "Falta campo m3_sal_periodo"
        assert 'm3_ent_hoy' not in data, "Campo antiguo m3_ent_hoy no debe existir"
        assert 'm3_sal_hoy' not in data, "Campo antiguo m3_sal_hoy no debe existir"

    def test_dashboard_sin_params_responde_200(self, client):
        """Sin params desde/hasta el endpoint usa hoy por defecto — no falla."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert 'ent_periodo' in data

    def test_dashboard_retorna_balance_y_total(self, client):
        """Los campos balance y total siguen presentes."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-04-11&hasta=2026-04-11', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert 'balance' in data
        assert 'total' in data
        assert data['balance'] >= 0

    def test_dashboard_fecha_invalida_devuelve_400(self, client):
        """Formato de fecha inválido debe retornar 400."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=no-es-fecha&hasta=2026-04-11', headers=AUTH)
        assert r.status_code == 400

    def test_dashboard_rango_invertido_devuelve_400(self, client):
        """desde > hasta debe retornar 400."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-04-11&hasta=2026-04-01', headers=AUTH)
        assert r.status_code == 400

    def test_dashboard_mismo_dia_desde_hasta_ok(self, client):
        """desde == hasta (un solo día) debe funcionar."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-04-11&hasta=2026-04-11', headers=AUTH)
        assert r.status_code == 200


class TestNombresFrecuentes:
    def test_dashboard_incluye_nombres_frecuentes(self, client):
        """La respuesta del dashboard incluye la lista nombres_frecuentes."""
        with patch('app.get_db', return_value=fake_db()):
            r = client.get('/api/dashboard?desde=2026-07-01&hasta=2026-07-31', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert 'nombres_frecuentes' in data, "Falta la clave nombres_frecuentes"
        assert isinstance(data['nombres_frecuentes'], list)

    def test_dashboard_nombres_frecuentes_sql_semantica(self, client):
        """La consulta agrupa por nombre normalizado, filtra ENTRADA y umbral > 3."""
        conn = fake_db()
        cur = conn.cursor.return_value
        with patch('app.get_db', return_value=conn):
            client.get('/api/dashboard?desde=2026-07-01&hasta=2026-07-31', headers=AUTH)
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        nf = [s for s in sqls if 'HAVING COUNT(*) > 3' in s]
        assert nf, "No se ejecutó la consulta de nombres frecuentes (HAVING COUNT(*) > 3)"
        sql = nf[0]
        assert "tipo='ENTRADA'" in sql, "La consulta debe filtrar solo ENTRADA"
        assert 'LOWER(TRIM(nombre))' in sql, "Debe agrupar por nombre normalizado"
