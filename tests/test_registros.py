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


# Payload base válido para POST de entrada (m3 > 0 y placa válida,
# obligatorios desde las validaciones de captura de 2026-07)
def entrada_valida(**extra):
    d = {'tipo': 'ENTRADA', 'fecha': '2026-07-15', 'pga': 'ESTERITO',
         'origen': 'NEGOCIO', 'placa': 'ABC-123-D', 'm3': 2.5}
    d.update(extra)
    return d


class TestCrearRegistroCalle:
    def test_post_registro_guarda_calle(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json=entrada_valida(
                nombre='Juan Perez', calle='Av. Reforma', colonia='Centro'
            ), headers=AUTH)
        assert r.status_code == 201

        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        assert insert_calls, "No se ejecutó el INSERT de registros"
        sql, params = insert_calls[0].args
        assert 'calle' in sql, "Falta la columna calle en el INSERT"
        assert _param_for_column(sql, params, 'calle') == 'Av. Reforma'

    def test_post_registro_sin_calle_guarda_cadena_vacia(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json=entrada_valida(), headers=AUTH)
        assert r.status_code == 201
        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        sql, params = insert_calls[0].args
        assert _param_for_column(sql, params, 'calle') == ''


class TestM3Obligatorio:
    def _post(self, client, payload):
        conn, _ = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            return client.post('/api/registros', json=payload, headers=AUTH)

    def test_entrada_sin_m3_devuelve_400(self, client):
        d = entrada_valida(); del d['m3']
        assert self._post(client, d).status_code == 400

    def test_entrada_m3_cero_devuelve_400(self, client):
        assert self._post(client, entrada_valida(m3=0)).status_code == 400

    def test_entrada_m3_invalido_devuelve_400(self, client):
        assert self._post(client, entrada_valida(m3='abc')).status_code == 400

    def test_salida_sin_m3_devuelve_400(self, client):
        r = self._post(client, {'tipo': 'SALIDA', 'fecha': '2026-07-15', 'pga': 'ESTERITO'})
        assert r.status_code == 400

    def test_salida_con_m3_ok(self, client):
        r = self._post(client, {'tipo': 'SALIDA', 'fecha': '2026-07-15',
                                'pga': 'ESTERITO', 'm3': 14})
        assert r.status_code == 201


class TestPlacaFormato:
    def _post(self, client, payload):
        conn, _ = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            return client.post('/api/registros', json=payload, headers=AUTH)

    def test_entrada_sin_placa_devuelve_400(self, client):
        d = entrada_valida(); del d['placa']
        assert self._post(client, d).status_code == 400

    def test_entrada_placa_corta_devuelve_400(self, client):
        assert self._post(client, entrada_valida(placa='D3')).status_code == 400

    def test_entrada_placa_larga_devuelve_400(self, client):
        assert self._post(client, entrada_valida(placa='ABC123DEF9')).status_code == 400

    def test_entrada_placa_7_alfanumericos_con_guiones_ok(self, client):
        # "EW-1057-D" → EW1057D = 7 alfanuméricos: válida
        assert self._post(client, entrada_valida(placa='EW-1057-D')).status_code == 201

    def test_entrada_sin_placas_especial_ok(self, client):
        assert self._post(client, entrada_valida(placa='SIN PLACAS')).status_code == 201

    def test_salida_sin_placa_ok(self, client):
        # El formato de placa solo aplica a entradas
        r = self._post(client, {'tipo': 'SALIDA', 'fecha': '2026-07-15',
                                'pga': 'ESTERITO', 'm3': 14})
        assert r.status_code == 201


class TestBuscarPlacaCalle:
    def test_buscar_placa_incluye_calle_en_respuesta(self, client):
        fila = {'vehiculo': 'CARROMATO', 'detalle': 'ESCOMBRO', 'origen': 'NEGOCIO',
                'nombre': 'Juan Perez', 'calle': 'Av. Reforma', 'colonia': 'Centro'}
        conn, cur = fake_db(fetchone_value=fila)
        with patch('app.get_db', return_value=conn):
            r = client.get('/api/registros/buscar-placa?q=ABC123', headers=AUTH)
        assert r.status_code == 200
        data = r.get_json()
        assert data['calle'] == 'Av. Reforma'

        select_calls = [
            c for c in cur.execute.call_args_list
            if c.args[0].strip().startswith('SELECT') and 'FROM registros' in c.args[0]
        ]
        assert select_calls, "No se ejecutó el SELECT de buscar-placa"
        assert 'calle' in select_calls[0].args[0], "Falta calle en el SELECT de buscar-placa"
