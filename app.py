from flask import Flask, request, jsonify, render_template, send_file, Response
import psycopg2
import psycopg2.extras
import os, io
from datetime import datetime, date
from functools import wraps

app = Flask(__name__)

# ── Configuración ──────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL')
AUTH_USER    = os.environ.get('AUTH_USER')
AUTH_PASS    = os.environ.get('AUTH_PASS')

if not DATABASE_URL:
    raise RuntimeError('Falta la variable de entorno DATABASE_URL')
if not AUTH_USER or not AUTH_PASS:
    raise RuntimeError('Faltan las variables de entorno AUTH_USER o AUTH_PASS')

# ── Base de datos ──────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Solo para desarrollo local. En producción usar migrate_data.py."""
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS registros (
                        id        SERIAL PRIMARY KEY,
                        folio     TEXT NOT NULL,
                        tipo      TEXT NOT NULL,
                        fecha     DATE NOT NULL,
                        hora      TEXT,
                        pga       TEXT NOT NULL,
                        detalle   TEXT,
                        origen    TEXT,
                        colonia   TEXT,
                        vehiculo  TEXT,
                        placa     TEXT,
                        m3        REAL DEFAULT 0,
                        obs       TEXT,
                        creado_en TIMESTAMP DEFAULT NOW()
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS config (
                        clave TEXT PRIMARY KEY,
                        valor TEXT
                    )
                ''')
                cur.execute(
                    "INSERT INTO config VALUES ('folio_base','1') ON CONFLICT DO NOTHING"
                )
    finally:
        conn.close()

# ── Autenticación ──────────────────────────────────────────────
def requiere_auth(f):
    @wraps(f)
    def decorado(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != AUTH_USER or auth.password != AUTH_PASS:
            return Response(
                'Acceso restringido',
                401,
                {'WWW-Authenticate': 'Basic realm="CT App"'}
            )
        return f(*args, **kwargs)
    return decorado

# ── Folio ──────────────────────────────────────────────────────
def next_folio(tipo, cur):
    """Genera el siguiente folio. Debe llamarse dentro de la misma transacción
    que el INSERT, para que el SELECT FOR UPDATE mantenga el lock."""
    cur.execute(
        "SELECT valor FROM config WHERE clave='folio_base' FOR UPDATE"
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Falta la fila 'folio_base' en la tabla config")
    n = int(row['valor'])
    prefix = 'ENT-' if tipo == 'ENTRADA' else 'SAL-'
    folio = prefix + str(n).zfill(4)
    cur.execute(
        "UPDATE config SET valor=%s WHERE clave='folio_base'", (n + 1,)
    )
    return folio

# ── Rutas ──────────────────────────────────────────────────────
@app.route('/')
@requiere_auth
def index():
    return render_template('index.html')

@app.route('/api/registros', methods=['GET'])
@requiere_auth
def get_registros():
    fecha = request.args.get('fecha')
    tipo  = request.args.get('tipo')
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                q = "SELECT * FROM registros WHERE 1=1"
                params = []
                if fecha:
                    q += " AND fecha=%s"; params.append(fecha)
                if tipo:
                    q += " AND tipo=%s"; params.append(tipo)
                q += " ORDER BY id DESC"
                cur.execute(q, params)
                rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/registros', methods=['POST'])
@requiere_auth
def crear_registro():
    d = request.get_json()
    if not d:
        return jsonify({'error': 'JSON requerido'}), 400
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                folio = next_folio(d.get('tipo', 'ENTRADA'), cur)
                cur.execute('''
                    INSERT INTO registros
                    (folio,tipo,fecha,hora,pga,detalle,origen,nombre,colonia,vehiculo,placa,m3,obs)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ''', (
                    folio,
                    d.get('tipo', 'ENTRADA'),
                    d.get('fecha', str(date.today())),
                    d.get('hora', ''),
                    d.get('pga', ''),
                    d.get('detalle', ''),
                    d.get('origen', ''),
                    d.get('nombre', ''),
                    d.get('colonia', ''),
                    d.get('vehiculo', ''),
                    d.get('placa', ''),
                    float(d.get('m3') or 0),
                    d.get('obs', '')
                ))
    finally:
        conn.close()
    return jsonify({'ok': True, 'folio': folio}), 201

@app.route('/api/registros/buscar-placa', methods=['GET'])
@requiere_auth
def buscar_placa():
    """Devuelve los datos del último registro de entrada con esa placa (parcial)."""
    q = request.args.get('q', '').strip().upper()
    if len(q) < 3:
        return jsonify(None)
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT vehiculo, detalle, origen, nombre, colonia
                    FROM registros
                    WHERE UPPER(placa) LIKE %s AND tipo='ENTRADA'
                    ORDER BY id DESC LIMIT 1
                """, (q + '%',))
                row = cur.fetchone()
    finally:
        conn.close()
    return jsonify(dict(row) if row else None)

@app.route('/api/registros/<int:rid>', methods=['DELETE'])
@requiere_auth
def eliminar_registro(rid):
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM registros WHERE id=%s", (rid,))
                if cur.rowcount == 0:
                    return jsonify({'error': 'Registro no encontrado'}), 404
                # Recalcular folio_base al número más alto existente + 1
                # Si no quedan registros, vuelve a 1
                cur.execute("""
                    UPDATE config SET valor = (
                        SELECT COALESCE(MAX(SUBSTRING(folio FROM 5)::INTEGER), 0) + 1
                        FROM registros
                    ) WHERE clave = 'folio_base'
                """)
    finally:
        conn.close()
    return jsonify({'ok': True})

@app.route('/api/dashboard', methods=['GET'])
@requiere_auth
def dashboard():
    _today = str(date.today())
    desde = request.args.get('desde', _today)
    hasta  = request.args.get('hasta',  _today)
    # Validate date format; fall back to today on bad input
    for _s in (desde, hasta):
        try:
            datetime.strptime(_s, '%Y-%m-%d')
        except (ValueError, TypeError):
            return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400
    if desde > hasta:
        return jsonify({'error': 'desde debe ser anterior o igual a hasta'}), 400
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                def q(sql, p=None):
                    cur.execute(sql, p or [])
                    return cur.fetchone()
                def qa(sql, p=None):
                    cur.execute(sql, p or [])
                    return cur.fetchall()

                ent_periodo = q(
                    "SELECT COUNT(*) c FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA'",
                    [desde, hasta])['c']
                sal_periodo = q(
                    "SELECT COUNT(*) c FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'",
                    [desde, hasta])['c']
                tot    = q("SELECT COUNT(*) c FROM registros")['c']
                m3_ep  = q(
                    "SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA'",
                    [desde, hasta])['v']
                m3_sp  = q(
                    "SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'",
                    [desde, hasta])['v']
                m3_et  = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE tipo='ENTRADA'")['v']
                m3_st  = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE tipo='SALIDA'")['v']

                pgas = ['ROVIROSA WADE', 'LEY SAULO', 'ESTERITO', 'RECOVERDE', 'COMPRESORA']
                pga_flow = []
                for p in pgas:
                    ei  = q(
                        "SELECT COUNT(*) c FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA' AND pga=%s",
                        [desde, hasta, p])['c']
                    so  = q(
                        "SELECT COUNT(*) c FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'  AND pga=%s",
                        [desde, hasta, p])['c']
                    m3i = q(
                        "SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA' AND pga=%s",
                        [desde, hasta, p])['v']
                    m3o = q(
                        "SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'  AND pga=%s",
                        [desde, hasta, p])['v']
                    pga_flow.append({
                        'pga': p, 'ent': ei, 'sal': so,
                        'm3_ent': round(float(m3i), 2),
                        'm3_sal': round(float(m3o), 2)
                    })

                origenes = ['NEGOCIO', 'RECOLECTORES', 'CASA-HABITACIÓN', 'CEA', 'LA OLA']
                origen_counts = []
                for o in origenes:
                    c = q("SELECT COUNT(*) c FROM registros WHERE tipo='ENTRADA' AND origen=%s", [o])['c']
                    if c:
                        origen_counts.append({'origen': o, 'count': c})
                otros = qa("""
                    SELECT origen, COUNT(*) c FROM registros
                    WHERE tipo='ENTRADA'
                      AND origen NOT IN ('NEGOCIO','RECOLECTORES','CASA-HABITACIÓN','PASA','LA OLA')
                      AND origen IS NOT NULL AND origen != '' AND origen != '—'
                    GROUP BY origen
                """)
                for r in otros:
                    origen_counts.append({'origen': r['origen'], 'count': r['c']})
                origen_counts.sort(key=lambda x: -x['count'])

                hist = qa("""
                    SELECT fecha,
                           SUM(CASE WHEN tipo='ENTRADA' THEN 1 ELSE 0 END) entradas,
                           SUM(CASE WHEN tipo='SALIDA'  THEN 1 ELSE 0 END) salidas
                    FROM registros
                    WHERE fecha BETWEEN %s AND %s
                    GROUP BY fecha ORDER BY fecha
                """, [desde, hasta])
    finally:
        conn.close()

    return jsonify({
        'ent_periodo': ent_periodo, 'sal_periodo': sal_periodo,
        'balance': max(0, ent_periodo - sal_periodo), 'total': tot,
        'm3_ent_periodo': round(float(m3_ep), 2), 'm3_sal_periodo': round(float(m3_sp), 2),
        'm3_ent_tot': round(float(m3_et), 2), 'm3_sal_tot': round(float(m3_st), 2),
        'pga_flow': pga_flow,
        'origen_counts': origen_counts,
        'historial': [dict(r) for r in hist]
    })

@app.route('/api/export/excel', methods=['GET'])
@requiere_auth
def export_excel():
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return jsonify({'error': 'openpyxl no instalado'}), 500

    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM registros ORDER BY id DESC")
                rows = cur.fetchall()
    finally:
        conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Registros'

    headers = ['ID', 'Folio', 'Tipo', 'Fecha', 'Hora', 'PGA', 'Detalle/Carga',
               'Origen', 'Colonia', 'Vehículo', 'Placa', 'm³', 'Observaciones', 'Registrado']
    header_fill = PatternFill(fill_type='solid', fgColor='1a6fc4')
    header_font = Font(bold=True, color='FFFFFF')
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for row in rows:
        ws.append([
            row['id'], row['folio'], row['tipo'], row['fecha'], row['hora'],
            row['pga'], row['detalle'], row['origen'], row['colonia'],
            row['vehiculo'], row['placa'], row['m3'], row['obs'], row['creado_en']
        ])

    col_widths = [6, 10, 8, 12, 8, 18, 18, 16, 18, 18, 12, 8, 30, 18]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"CT_Viajes_{date.today()}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    init_db()
    app.run()
