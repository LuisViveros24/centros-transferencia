# Migración ct_app_mac → Render.com (PostgreSQL) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar la app Flask de SQLite local a PostgreSQL en Render.com con HTTP Basic Auth, para acceso público desde cualquier navegador.

**Architecture:** psycopg2 directo (sin ORM), patrón `get_db()` / `try-finally conn.close()` con `RealDictCursor`, decorador `@requiere_auth` en las 6 rutas. El esquema se crea una sola vez con `migrate_data.py`, ya que Gunicorn no ejecuta `if __name__ == '__main__'`.

**Tech Stack:** Python 3, Flask, psycopg2-binary, Gunicorn, openpyxl, Render.com (plan free), PostgreSQL 15.

---

## Archivos del proyecto

```
ct_app_mac/
  app.py                ← MODIFICAR: SQLite → PostgreSQL + Basic Auth
  requirements.txt      ← CREAR: dependencias de producción
  render.yaml           ← CREAR: config de infraestructura en Render
  migrate_data.py       ← CREAR: crea tablas en PostgreSQL (una sola vez)
  README_DEPLOY.md      ← CREAR: guía paso a paso para supervisores
  templates/
    index.html          ← sin cambios
```

---

## Prerequisito: Repositorio Git

> **Nota:** El repositorio ya fue inicializado con `git init` durante la fase de diseño y contiene 2 commits (los docs de spec). Si estás partiendo de cero, ejecuta primero:
>
> ```bash
> cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
> git init
> git add docs/
> git commit -m "docs: add design spec"
> ```
>
> También asegúrate de tener un `.gitignore` que evite subir la DB y archivos de Python:
>
> ```
> *.db
> __pycache__/
> *.pyc
> .env
> ```
>
> ```bash
> echo "*.db\n__pycache__/\n*.pyc\n.env" > .gitignore
> git add .gitignore
> git commit -m "chore: add .gitignore"
> ```

---

## Task 1: Crear `requirements.txt`

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Crear el archivo con las dependencias exactas**

```
flask
psycopg2-binary
gunicorn
openpyxl
```

Guardar en la raíz del proyecto como `requirements.txt`.

- [ ] **Step 2: Verificar que pip puede leerlo sin errores**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
pip install -r requirements.txt --dry-run
```

Expected: lista de paquetes a instalar, sin errores de sintaxis.

- [ ] **Step 3: Commit**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
git add requirements.txt
git commit -m "feat: add requirements.txt for Render deployment"
```

---

## Task 2: Crear `render.yaml`

**Files:**
- Create: `render.yaml`

- [ ] **Step 1: Crear el archivo**

```yaml
services:
  - type: web
    name: ct-app
    runtime: python
    plan: free
    region: oregon
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: ct-db
          property: connectionString
      - key: AUTH_USER
        sync: false
      - key: AUTH_PASS
        sync: false

databases:
  - name: ct-db
    plan: free
    region: oregon
    databaseName: centros_transferencia
```

- [ ] **Step 2: Verificar sintaxis YAML**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
python -c "import yaml; yaml.safe_load(open('render.yaml')); print('YAML OK')"
```

Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "feat: add render.yaml for Render Blueprint deployment"
```

---

## Task 3: Reescribir `app.py` con PostgreSQL y Basic Auth

**Files:**
- Modify: `app.py`

Esta es la tarea central. Se reemplaza el contenido completo del archivo. Los cambios respecto al original son:
1. `sqlite3` → `psycopg2` + `psycopg2.extras`
2. Validación de env vars al arrancar (RuntimeError si faltan)
3. Decorador `@requiere_auth` en todas las rutas
4. Patrón `conn = get_db() / try / with conn / finally conn.close()`
5. `?` → `%s` en todas las queries
6. `next_folio()` recibe el cursor activo (misma transacción que el INSERT)
7. `fecha DATE` en lugar de `TEXT`; historial usa `%s::date - INTERVAL '13 days'`
8. `COALESCE` retorna `Decimal` en psycopg2 → envolver en `float()` antes de `round()`

- [ ] **Step 1: Escribir el nuevo `app.py` completo**

```python
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
    n = int(cur.fetchone()['valor'])
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
    conn = get_db()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                folio = next_folio(d.get('tipo', 'ENTRADA'), cur)
                cur.execute('''
                    INSERT INTO registros
                    (folio,tipo,fecha,hora,pga,detalle,origen,colonia,vehiculo,placa,m3,obs)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ''', (
                    folio,
                    d.get('tipo', 'ENTRADA'),
                    d.get('fecha', str(date.today())),
                    d.get('hora', ''),
                    d.get('pga', ''),
                    d.get('detalle', ''),
                    d.get('origen', ''),
                    d.get('colonia', ''),
                    d.get('vehiculo', ''),
                    d.get('placa', ''),
                    float(d.get('m3') or 0),
                    d.get('obs', '')
                ))
    finally:
        conn.close()
    return jsonify({'ok': True, 'folio': folio}), 201

@app.route('/api/registros/<int:rid>', methods=['DELETE'])
@requiere_auth
def eliminar_registro(rid):
    conn = get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM registros WHERE id=%s", (rid,))
    finally:
        conn.close()
    return jsonify({'ok': True})

@app.route('/api/dashboard', methods=['GET'])
@requiere_auth
def dashboard():
    hoy = request.args.get('fecha', str(date.today()))
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

                ent_hoy = q("SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='ENTRADA'", [hoy])['c']
                sal_hoy = q("SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='SALIDA'",  [hoy])['c']
                tot     = q("SELECT COUNT(*) c FROM registros")['c']
                m3_eh   = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha=%s AND tipo='ENTRADA'", [hoy])['v']
                m3_sh   = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha=%s AND tipo='SALIDA'",  [hoy])['v']
                m3_et   = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE tipo='ENTRADA'")['v']
                m3_st   = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE tipo='SALIDA'")['v']

                pgas = ['ROVIROSA WADE', 'LEY SAULO', 'ESTERITO', 'RECOVERDE', 'COMPRESORA']
                pga_flow = []
                for p in pgas:
                    ei  = q("SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='ENTRADA' AND pga=%s", [hoy, p])['c']
                    so  = q("SELECT COUNT(*) c FROM registros WHERE fecha=%s AND tipo='SALIDA'  AND pga=%s", [hoy, p])['c']
                    m3i = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha=%s AND tipo='ENTRADA' AND pga=%s", [hoy, p])['v']
                    m3o = q("SELECT COALESCE(SUM(m3),0) v FROM registros WHERE fecha=%s AND tipo='SALIDA'  AND pga=%s", [hoy, p])['v']
                    pga_flow.append({
                        'pga': p, 'ent': ei, 'sal': so,
                        'm3_ent': round(float(m3i), 2),
                        'm3_sal': round(float(m3o), 2)
                    })

                origenes = ['NEGOCIO', 'RECOLECTORES', 'CASA-HABITACIÓN', 'PASA', 'LA OLA']
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
                    WHERE fecha >= (%s::date - INTERVAL '13 days')
                    GROUP BY fecha ORDER BY fecha
                """, [hoy])
    finally:
        conn.close()

    return jsonify({
        'ent_hoy': ent_hoy, 'sal_hoy': sal_hoy,
        'balance': max(0, ent_hoy - sal_hoy), 'total': tot,
        'm3_ent_hoy': round(float(m3_eh), 2), 'm3_sal_hoy': round(float(m3_sh), 2),
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
```

- [ ] **Step 2: Escribir tests de autenticación (no requieren BD)**

Crear `tests/test_auth.py`:

```python
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
```

- [ ] **Step 3: Instalar pytest y ejecutar los tests**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
pip install pytest
pytest tests/test_auth.py -v
```

Expected: 7 tests, todos en PASSED.  
Si alguno falla con `ModuleNotFoundError: psycopg2`, instalar antes: `pip install psycopg2-binary`.

- [ ] **Step 4: Verificar que el módulo levanta error si faltan las variables de entorno**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
python -c "
import os, sys
# Limpiar variables si existen
for k in ['DATABASE_URL','AUTH_USER','AUTH_PASS']:
    os.environ.pop(k, None)
if 'app' in sys.modules: del sys.modules['app']
try:
    import app
    print('ERROR: debería haber lanzado RuntimeError')
except RuntimeError as e:
    print(f'OK: RuntimeError lanzado correctamente → {e}')
"
```

Expected: `OK: RuntimeError lanzado correctamente → Falta la variable de entorno DATABASE_URL`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_auth.py
git commit -m "feat: migrate app.py to PostgreSQL with Basic Auth"
```

---

## Task 4: Crear `migrate_data.py`

**Files:**
- Create: `migrate_data.py`

- [ ] **Step 1: Crear el script**

```python
"""
migrate_data.py — Inicializa el esquema PostgreSQL en Render.

Ejecutar UNA SOLA VEZ desde terminal local, usando la External Database URL
de Render (Dashboard → ct-db → Connections → External Database URL).

Uso:
    DATABASE_URL="postgresql://..." python migrate_data.py
"""
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise SystemExit(
        'ERROR: Define DATABASE_URL antes de correr este script.\n'
        'Ejemplo:\n'
        '  DATABASE_URL="postgresql://user:pass@host/db" python migrate_data.py'
    )

print('Conectando a PostgreSQL...')
conn = psycopg2.connect(DATABASE_URL)

try:
    with conn:
        with conn.cursor() as cur:
            print('Creando tabla registros...')
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
            print('Creando tabla config...')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    clave TEXT PRIMARY KEY,
                    valor TEXT
                )
            ''')
            print('Insertando contador de folio inicial...')
            cur.execute(
                "INSERT INTO config VALUES ('folio_base', '1') ON CONFLICT DO NOTHING"
            )
    print('\n✓ Esquema creado correctamente en PostgreSQL.')
    print('  Puedes hacer un Manual Deploy en Render ahora.')
finally:
    conn.close()
```

- [ ] **Step 2: Verificar que el script falla correctamente sin DATABASE_URL**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
python migrate_data.py
```

Expected: mensaje de error claro indicando que falta `DATABASE_URL`.  
No debe haber traceback crudo — solo el mensaje de `SystemExit`.

- [ ] **Step 3: Commit**

```bash
git add migrate_data.py
git commit -m "feat: add migrate_data.py to initialize PostgreSQL schema"
```

---

## Task 5: Crear `README_DEPLOY.md`

**Files:**
- Create: `README_DEPLOY.md`

- [ ] **Step 1: Crear la guía de despliegue**

```markdown
# Centros de Transferencia — Guía de Despliegue en Render.com

Esta guía explica cómo poner la app en internet para que los supervisores
puedan acceder desde cualquier navegador.

---

## Requisitos previos

- Cuenta de GitHub con el repositorio `centros-transferencia` subido
- Cuenta en [Render.com](https://render.com) (gratuita)

---

## Paso 1 — Crear cuenta en Render y conectar GitHub

1. Ir a [render.com](https://render.com) → **Sign Up**
2. Seleccionar **Continue with GitHub**
3. Autorizar a Render el acceso al repositorio `centros-transferencia`

---

## Paso 2 — Crear el Blueprint (BD + Web Service automáticos)

1. En el dashboard de Render → **New +** → **Blueprint**
2. Seleccionar el repositorio `centros-transferencia`
3. Render detecta el archivo `render.yaml` y muestra un resumen:
   - Un **Web Service** llamado `ct-app` (plan Free, región Oregon)
   - Una **Base de datos PostgreSQL** llamada `ct-db` (plan Free, región Oregon)
4. Hacer clic en **Apply**

> ⚠️ **El primer deploy fallará** con un error de base de datos — esto es **normal y esperado**.
> Las tablas todavía no existen. Continúa con los siguientes pasos antes de
> preocuparte por el error.

---

## Paso 3 — Agregar las credenciales de acceso

1. En el dashboard de Render → seleccionar el servicio **ct-app**
2. Ir a la pestaña **Environment**
3. Hacer clic en **Add Environment Variable** y agregar dos entradas:

   | Key | Value |
   |-----|-------|
   | `AUTH_USER` | `PGA2627` |
   | `AUTH_PASS` | `Limpie$a2627` |

4. Hacer clic en **Save Changes**

> ℹ️ Estas credenciales nunca aparecen en el código ni en GitHub.
> Solo existen dentro del ambiente seguro de Render.

---

## Paso 4 — Obtener la URL de conexión externa de la base de datos

1. En el dashboard de Render → seleccionar el servicio **ct-db**
2. Ir a la pestaña **Connections**
3. Copiar el campo **"External Database URL"**
   - Empieza con `postgresql://...`
   - ⚠️ **No copiar** la "Internal Database URL" — esa solo funciona dentro de Render

---

## Paso 5 — Crear las tablas (una sola vez)

Desde una terminal en tu computadora, ejecutar:

```bash
DATABASE_URL="<pegar aquí la External Database URL>" python migrate_data.py
```

Reemplazar `<pegar aquí la External Database URL>` con lo que copiaste en el Paso 4.

Expected output:
```
Conectando a PostgreSQL...
Creando tabla registros...
Creando tabla config...
Insertando contador de folio inicial...

✓ Esquema creado correctamente en PostgreSQL.
  Puedes hacer un Manual Deploy en Render ahora.
```

---

## Paso 6 — Redeploy manual

1. En el dashboard de Render → seleccionar el servicio **ct-app**
2. Hacer clic en **Manual Deploy** → **Deploy latest commit**
3. Esperar ~2 minutos a que termine el deploy
4. El estado cambiará a **Live** ✅

---

## Paso 7 — Compartir la URL con los supervisores

1. En la página del servicio `ct-app` en Render, copiar la URL pública
   - Ejemplo: `https://ct-app.onrender.com`
2. Enviar esa URL a los supervisores

Los supervisores entrarán al link, el navegador pedirá usuario y contraseña,
y podrán usar la app normalmente.

---

## Notas importantes

- **Primer acceso lento:** El plan gratuito de Render pausa el servicio tras
  15 minutos de inactividad. El primer acceso después de una pausa tarda ~30 segundos
  en despertar — esto es normal, no un error.

- **HTTPS incluido:** Render provee HTTPS automáticamente. La contraseña viaja
  cifrada.

- **Actualizaciones futuras:** Cada vez que se suba código nuevo a GitHub
  (`git push`), Render desplegará automáticamente la nueva versión.
```

- [ ] **Step 2: Verificar que el Markdown se renderiza sin errores**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
python -c "
with open('README_DEPLOY.md') as f:
    content = f.read()
# Verificar que los pasos estén todos presentes
pasos = ['Paso 1', 'Paso 2', 'Paso 3', 'Paso 4', 'Paso 5', 'Paso 6', 'Paso 7']
for p in pasos:
    assert p in content, f'Falta {p}'
print('README_DEPLOY.md OK — todos los pasos presentes')
"
```

Expected: `README_DEPLOY.md OK — todos los pasos presentes`

- [ ] **Step 3: Commit**

```bash
git add README_DEPLOY.md
git commit -m "docs: add step-by-step deployment guide for Render.com"
```

---

## Task 6: Push a GitHub y verificación final

**Files:** ninguno nuevo — solo git push

- [ ] **Step 1: Verificar el estado completo del repositorio**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
git status
git log --oneline
```

Expected: working tree limpio, al menos 5 commits en el log (uno por cada Task 1–5), más los commits de spec del prerequisito.

- [ ] **Step 2: Verificar que todos los archivos necesarios existen**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
python -c "
import os
required = ['app.py', 'requirements.txt', 'render.yaml', 'migrate_data.py', 'README_DEPLOY.md']
for f in required:
    exists = os.path.exists(f)
    print(f'{'✓' if exists else '✗'} {f}')
assert all(os.path.exists(f) for f in required), 'Faltan archivos'
print('Todos los archivos presentes')
"
```

Expected: ✓ en los 5 archivos.

- [ ] **Step 3: Ejecutar los tests una última vez**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
pytest tests/test_auth.py -v
```

Expected: 7 tests en PASSED.

- [ ] **Step 4: Conectar el repositorio remoto y hacer push**

```bash
cd "/Users/viverosmunoz/Desktop/Sistemas de Reportes/ct_app_mac"
git remote add origin https://github.com/LuisViveros24/centros-transferencia.git
git branch -M main
git push -u origin main
```

Expected: todos los archivos subidos a GitHub sin errores.

- [ ] **Step 5: Verificar en GitHub**

Abrir `https://github.com/LuisViveros24/centros-transferencia` en el navegador y confirmar que aparecen:
- `app.py`
- `requirements.txt`
- `render.yaml`
- `migrate_data.py`
- `README_DEPLOY.md`
- `templates/index.html`

---

## Checklist de éxito final (verificar en Render después del deploy)

- [ ] La app responde en la URL pública de Render
- [ ] El navegador pide usuario y contraseña al entrar
- [ ] Credenciales incorrectas → sigue pidiendo contraseña (no entra)
- [ ] Credenciales correctas (`PGA2627` / `Limpie$a2627`) → entra a la app
- [ ] Se puede crear un registro de prueba y aparece en la lista
- [ ] Se puede eliminar el registro de prueba
- [ ] El Dashboard muestra estadísticas (aunque sean en 0)
- [ ] El botón Exportar Excel descarga un `.xlsx` válido
- [ ] Los folios se generan en secuencia: `ENT-0001`, `ENT-0002`, etc.
