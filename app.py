from flask import Flask, request, jsonify, render_template, send_file, Response, g, make_response
import psycopg2
import psycopg2.extras
import os, io, re, hmac
from datetime import datetime, date
from functools import wraps

app = Flask(__name__)

# ── Configuración ──────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL')
AUTH_USER    = os.environ.get('AUTH_USER')
AUTH_PASS    = os.environ.get('AUTH_PASS')
# Opcionales: si están configuradas, AUTH_USER queda restringido a captura
# y ADMIN_USER tiene acceso total. Si no, AUTH_USER conserva acceso total
# (migración segura: el deploy no rompe nada antes de configurarlas en Render).
ADMIN_USER   = os.environ.get('ADMIN_USER')
ADMIN_PASS   = os.environ.get('ADMIN_PASS')

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
                        nombre    TEXT,
                        calle     TEXT,
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
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS colonias_geo (
                        colonia_norm TEXT PRIMARY KEY,
                        lat          REAL,
                        lng          REAL,
                        estado       TEXT NOT NULL,
                        creado_en    TIMESTAMP DEFAULT NOW()
                    )
                ''')
                cur.execute(
                    "INSERT INTO config VALUES ('folio_base','1') ON CONFLICT DO NOTHING"
                )
    finally:
        conn.close()

# ── Autenticación y roles ──────────────────────────────────────
def _cred_ok(auth, exp_user, exp_pass):
    if not exp_user or not exp_pass or not auth or auth.username is None or auth.password is None:
        return False
    return hmac.compare_digest(auth.username, exp_user) and \
           hmac.compare_digest(auth.password, exp_pass)

def _rol_de(auth):
    """'admin', 'captura' o None según las credenciales recibidas."""
    if _cred_ok(auth, ADMIN_USER, ADMIN_PASS):
        return 'admin'
    if _cred_ok(auth, AUTH_USER, AUTH_PASS):
        # Sin admin configurado, el usuario de captura conserva acceso total
        return 'captura' if (ADMIN_USER and ADMIN_PASS) else 'admin'
    return None

def _respuesta_401():
    return Response(
        'Acceso restringido',
        401,
        {'WWW-Authenticate': 'Basic realm="CT App"'}
    )

def requiere_auth(f):
    """Cualquier usuario válido (captura o admin)."""
    @wraps(f)
    def decorado(*args, **kwargs):
        rol = _rol_de(request.authorization)
        if rol is None:
            return _respuesta_401()
        g.rol = rol
        return f(*args, **kwargs)
    return decorado

def requiere_admin(f):
    """Solo el usuario administrador."""
    @wraps(f)
    def decorado(*args, **kwargs):
        rol = _rol_de(request.authorization)
        if rol is None:
            return _respuesta_401()
        if rol != 'admin':
            return jsonify({'error': 'Se requiere usuario administrador'}), 403
        g.rol = rol
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
    # no-store: el navegador siempre pide la versión más reciente del HTML.
    # Evita que un operador quede con una copia vieja en caché tras un deploy
    # (frontend viejo + backend nuevo = errores confusos).
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    return resp

@app.route('/logout')
def logout():
    """Cierre de sesión para HTTP Basic Auth. Responde 401 SIEMPRE (aunque
    lleguen credenciales válidas) con el mismo realm de la app, para que el
    navegador considere inválidas las credenciales cacheadas y vuelva a pedir
    usuario y contraseña en el siguiente acceso."""
    return Response(
        'Sesión cerrada. Para volver a entrar, abre de nuevo la aplicación.',
        401,
        {'WWW-Authenticate': 'Basic realm="CT App"', 'Cache-Control': 'no-store'}
    )

@app.route('/api/whoami', methods=['GET'])
@requiere_auth
def whoami():
    """Rol del usuario autenticado; el frontend adapta la navegación."""
    return jsonify({'rol': g.rol})

@app.route('/api/badges', methods=['GET'])
@requiere_auth
def badges():
    """Conteo de entradas/salidas de una fecha, para los badges del menú.
    Accesible a captura (a diferencia de GET /api/registros, que es admin)."""
    fecha = request.args.get('fecha', str(date.today()))
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
    except (ValueError, TypeError):
        return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='ENTRADA'", [fecha])
                ent = cur.fetchone()['c']
                cur.execute(
                    "SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='SALIDA'", [fecha])
                sal = cur.fetchone()['c']
    finally:
        conn.close()
    return jsonify({'ent': ent, 'sal': sal})

@app.route('/api/registros', methods=['GET'])
@requiere_admin
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

    # m³ obligatorio y mayor a 0 (entradas y salidas)
    try:
        m3 = float(d.get('m3'))
    except (TypeError, ValueError):
        m3 = 0
    if m3 <= 0:
        return jsonify({'error': 'Los metros cúbicos son obligatorios y deben ser mayores a 0'}), 400

    # Placa obligatoria en entradas: 6-8 alfanuméricos (ignorando espacios
    # y guiones) o el valor especial SIN PLACAS. Regla validada contra los
    # datos de producción (94% de las placas tienen 7 alfanuméricos).
    if d.get('tipo', 'ENTRADA') == 'ENTRADA':
        placa_norm = re.sub(r'[^A-Z0-9]', '', str(d.get('placa') or '').upper())
        if placa_norm != 'SINPLACAS' and not (6 <= len(placa_norm) <= 8):
            return jsonify({'error': 'Placa inválida: escribe de 6 a 8 letras/números, o "SIN PLACAS"'}), 400

    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                folio = next_folio(d.get('tipo', 'ENTRADA'), cur)
                cur.execute('''
                    INSERT INTO registros
                    (folio,tipo,fecha,hora,pga,detalle,origen,nombre,calle,colonia,vehiculo,placa,m3,obs)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ''', (
                    folio,
                    d.get('tipo', 'ENTRADA'),
                    d.get('fecha', str(date.today())),
                    d.get('hora', ''),
                    d.get('pga', ''),
                    d.get('detalle', ''),
                    d.get('origen', ''),
                    d.get('nombre', ''),
                    d.get('calle', ''),
                    d.get('colonia', ''),
                    d.get('vehiculo', ''),
                    d.get('placa', ''),
                    m3,
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
                    SELECT vehiculo, detalle, origen, nombre, calle, colonia
                    FROM registros
                    WHERE UPPER(placa) LIKE %s AND tipo='ENTRADA'
                    ORDER BY id DESC LIMIT 1
                """, (q + '%',))
                row = cur.fetchone()
    finally:
        conn.close()
    return jsonify(dict(row) if row else None)

@app.route('/api/registros/<int:rid>', methods=['DELETE'])
@requiere_admin
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

def _colonias_para_mapa(rows):
    """Agrupa filas (norm, colonia, lat, lng, origen, c) por colonia:
    calcula el total de entradas y el origen dominante (el de mayor
    conteo) de cada una. Devuelve la lista ordenada por conteo desc."""
    por_colonia = {}
    for r in rows:
        if r['lat'] is None or r['lng'] is None:
            continue  # defensivo: fila sin coordenadas no debe tumbar el endpoint
        d = por_colonia.setdefault(r['norm'], {
            'colonia': r['colonia'], 'lat': float(r['lat']), 'lng': float(r['lng']),
            'total': 0, '_origenes': {}})
        c = int(r['c'])
        d['total'] += c
        o = r['origen'] or '—'
        d['_origenes'][o] = d['_origenes'].get(o, 0) + c
    salida = []
    for d in por_colonia.values():
        origen_dom = max(d['_origenes'].items(), key=lambda kv: kv[1])[0] if d['_origenes'] else '—'
        salida.append({'colonia': d['colonia'], 'lat': d['lat'], 'lng': d['lng'],
                       'origen': origen_dom, 'count': d['total']})
    salida.sort(key=lambda x: -x['count'])
    return salida

@app.route('/api/mapa', methods=['GET'])
@requiere_admin
def mapa_colonias():
    """Colonias de origen de las ENTRADAS del periodo con coordenadas
    (desde el caché colonias_geo), con su origen dominante. Solo aparecen
    las colonias que geocode_colonias.py pudo ubicar (estado='ok')."""
    _today = str(date.today())
    desde = request.args.get('desde', _today)
    hasta = request.args.get('hasta', _today)
    for _s in (desde, hasta):
        try:
            datetime.strptime(_s, '%Y-%m-%d')
        except (ValueError, TypeError):
            return jsonify({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400
    if desde > hasta:
        return jsonify({'error': 'desde debe ser anterior o igual a hasta'}), 400
    pga_filtro = request.args.get('pga', '').strip()

    params = [desde, hasta]
    pga_clause = ''
    if pga_filtro:
        pga_clause = ' AND r.pga = %s'
        params.append(pga_filtro)

    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT LOWER(TRIM(r.colonia)) AS norm, MAX(TRIM(r.colonia)) AS colonia, "
                    "r.origen AS origen, COUNT(*) AS c, cg.lat AS lat, cg.lng AS lng "
                    "FROM registros r "
                    "JOIN colonias_geo cg ON cg.colonia_norm = LOWER(TRIM(r.colonia)) "
                    "WHERE r.tipo='ENTRADA' AND cg.estado='ok' "
                    "AND r.fecha BETWEEN %s AND %s "
                    "AND r.colonia IS NOT NULL AND TRIM(r.colonia) != ''"
                    + pga_clause +
                    " GROUP BY LOWER(TRIM(r.colonia)), r.origen, cg.lat, cg.lng",
                    params)
                rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify({'colonias': _colonias_para_mapa(rows)})

@app.route('/api/dashboard', methods=['GET'])
@requiere_admin
def dashboard():
    _today = str(date.today())
    desde = request.args.get('desde', _today)
    hasta  = request.args.get('hasta',  _today)
    origen_filtro = request.args.get('origen', '').strip()
    pga_filtro = request.args.get('pga', '').strip()
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

                origenes = ['NEGOCIO', 'RECOLECTORES', 'CASA-HABITACIÓN', 'CEA', 'LA OLA', 'CONTRATISTAS']
                origen_counts = []
                for o in origenes:
                    c = q("SELECT COUNT(*) c FROM registros WHERE tipo='ENTRADA' AND origen=%s", [o])['c']
                    if c:
                        origen_counts.append({'origen': o, 'count': c})
                otros = qa("""
                    SELECT origen, COUNT(*) c FROM registros
                    WHERE tipo='ENTRADA'
                      AND origen NOT IN ('NEGOCIO','RECOLECTORES','CASA-HABITACIÓN','CEA','LA OLA','CONTRATISTAS')
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

                # Personas frecuentes: sin filtro de origen usa umbral > 3;
                # con un origen específico baja a > 1 (cada persona reparte sus
                # entradas entre varios orígenes, así que el conteo por origen es menor).
                # El umbral es un entero de nuestro propio código (1 o 3), no entrada
                # del usuario; el origen sí va como parámetro para evitar inyección.
                _nf_params = [desde, hasta]
                _nf_clauses = ''
                _nf_umbral = 3
                if origen_filtro:
                    _nf_clauses += ' AND origen = %s'
                    _nf_params.append(origen_filtro)
                    _nf_umbral = 1
                if pga_filtro:
                    _nf_clauses += ' AND pga = %s'
                    _nf_params.append(pga_filtro)
                nombres_frecuentes = qa(
                    "SELECT (ARRAY_AGG(nombre ORDER BY id DESC))[1] AS nombre, COUNT(*) AS c "
                    "FROM registros "
                    "WHERE tipo='ENTRADA' AND fecha BETWEEN %s AND %s"
                    + _nf_clauses +
                    " AND nombre IS NOT NULL AND TRIM(nombre) != '' "
                    "GROUP BY LOWER(TRIM(nombre)) "
                    "HAVING COUNT(*) > " + str(_nf_umbral) + " "
                    "ORDER BY c DESC",
                    _nf_params)
    finally:
        conn.close()

    return jsonify({
        'ent_periodo': ent_periodo, 'sal_periodo': sal_periodo,
        'balance': max(0, ent_periodo - sal_periodo), 'total': tot,
        'm3_ent_periodo': round(float(m3_ep), 2), 'm3_sal_periodo': round(float(m3_sp), 2),
        'm3_ent_tot': round(float(m3_et), 2), 'm3_sal_tot': round(float(m3_st), 2),
        'pga_flow': pga_flow,
        'origen_counts': origen_counts,
        'nombres_frecuentes': [{'nombre': r['nombre'], 'count': r['c']} for r in nombres_frecuentes],
        'historial': [dict(r) for r in hist]
    })

@app.route('/api/export/excel', methods=['GET'])
@requiere_admin
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
               'Origen', 'Nombre', 'Calle', 'Colonia', 'Vehículo', 'Placa', 'm³', 'Observaciones', 'Registrado']
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
            row['pga'], row['detalle'], row['origen'], row['nombre'], row['calle'], row['colonia'],
            row['vehiculo'], row['placa'], row['m3'], row['obs'], row['creado_en']
        ])

    col_widths = [6, 10, 8, 12, 8, 18, 18, 16, 22, 18, 18, 18, 12, 8, 30, 18]
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
