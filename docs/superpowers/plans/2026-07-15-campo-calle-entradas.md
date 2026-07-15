# Campo "Calle" en Registro de entrada — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Calle" field to the Entrada form, persist it end-to-end (DB, POST, autocomplete, Historial, Excel export), scoped to Entrada only.

**Architecture:** Follows the existing `colonia` field pattern exactly — same DB column shape, same POST payload key, same autocomplete SELECT, same Historial column, same Excel column. Three files: `app.py` (schema + 3 endpoints), `migrate_data.py` (production ALTER TABLE), `templates/index.html` (form field + JS wiring + Historial column). Also fixes a pre-existing gap found during spec review: `init_db()`'s local-dev schema is missing the `nombre` column that `crear_registro()` already inserts into unconditionally.

**Tech Stack:** Flask, psycopg2, vanilla JS, pytest with mocked `psycopg2` connections (see `tests/test_dashboard.py` for the established mocking pattern).

**Spec:** `docs/superpowers/specs/2026-07-15-campo-calle-entradas-design.md`

---

## File Map

| File | What changes |
|---|---|
| `app.py` | `init_db()` (~lines 31-48): add `nombre`, `calle` columns. `crear_registro()` (~lines 121-153): add `calle` to INSERT. `buscar_placa()` (~lines 155-175): add `calle` to SELECT. `export_excel()` (~lines 299-347): add "Nombre"/"Calle" headers + row values + col widths |
| `migrate_data.py` | Add `ALTER TABLE registros ADD COLUMN IF NOT EXISTS calle TEXT`, next to the existing `nombre` one |
| `templates/index.html` | CSS: new `.cols-4` class (3 places). Entrada form (~lines 253-274): add `e-calle` input, change row to `cols-4`. `registrarEntrada()` (~line 627): send `calle`. `limpiarE()` (~line 590): reset `e-calle`. `aplicarAutocompletado()` (~line 934): apply `calle`. Historial header (~line 439) and row render (~line 844): add "Calle" column |
| `tests/test_init_db.py` | New file — verifies `init_db()` schema includes `nombre` and `calle` |
| `tests/test_registros.py` | New file — verifies `calle` flows through POST `/api/registros` and GET `/api/registros/buscar-placa` |
| `tests/test_export.py` | New file — verifies Excel export includes "Nombre" and "Calle" columns |

No changes to `/api/dashboard`, the Salida form, or any Salida backend path.

---

## Task 1: Backend — `init_db()` includes `nombre` and `calle`

**Files:**
- Modify: `app.py:31-48`
- Create: `tests/test_init_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_init_db.py`:

```python
"""
Tests para init_db() — verifica que el esquema local (desarrollo)
incluya las columnas nombre y calle en la tabla registros.

nombre ya se usaba sin estar en este CREATE TABLE (brecha preexistente,
detectada durante la revisión del spec de 2026-07-15); calle es nueva.
"""
import os, sys
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('AUTH_USER', 'usuario_test')
os.environ.setdefault('AUTH_PASS', 'clave_test')

if 'app' in sys.modules:
    del sys.modules['app']

import app as app_module


def fake_db():
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


class TestInitDbSchema:
    def test_create_table_incluye_nombre_y_calle(self):
        conn, cur = fake_db()
        with patch('app.get_db', return_value=conn):
            app_module.init_db()

        create_calls = [
            c.args[0] for c in cur.execute.call_args_list
            if 'CREATE TABLE IF NOT EXISTS registros' in c.args[0]
        ]
        assert create_calls, "No se ejecutó el CREATE TABLE de registros"
        sql = create_calls[0]
        assert 'nombre' in sql, "Falta columna nombre en el CREATE TABLE (brecha preexistente sin corregir)"
        assert 'calle' in sql, "Falta columna calle en el CREATE TABLE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_init_db.py -v`
Expected: FAIL — `AssertionError: Falta columna calle en el CREATE TABLE` (and/or the `nombre` assertion, since neither is in the current `CREATE TABLE`)

- [ ] **Step 3: Write minimal implementation**

In `app.py`, inside `init_db()`, the `CREATE TABLE IF NOT EXISTS registros` block currently reads (lines 32-48):

```python
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
```

Change the `origen`/`colonia` lines to:

```python
                        origen    TEXT,
                        nombre    TEXT,
                        calle     TEXT,
                        colonia   TEXT,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_init_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_init_db.py
git commit -m "fix: init_db() incluye columnas nombre y calle en registros"
```

---

## Task 2: Backend — `POST /api/registros` incluye `calle`

**Files:**
- Modify: `app.py:121-153` (`crear_registro`)
- Create: `tests/test_registros.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_registros.py`:

```python
"""
Tests para POST /api/registros (incluye calle) y
GET /api/registros/buscar-placa (autocompletado incluye calle).
"""
import os, sys, base64, pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('AUTH_USER', 'usuario_test')
os.environ.setdefault('AUTH_PASS', 'clave_test')

if 'app' in sys.modules:
    del sys.modules['app']

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


class TestCrearRegistroCalle:
    def test_post_registro_guarda_calle(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json={
                'tipo': 'ENTRADA', 'fecha': '2026-07-15', 'pga': 'ESTERITO',
                'origen': 'NEGOCIO', 'nombre': 'Juan Perez',
                'calle': 'Av. Reforma', 'colonia': 'Centro'
            }, headers=AUTH)
        assert r.status_code == 201

        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        assert insert_calls, "No se ejecutó el INSERT de registros"
        sql, params = insert_calls[0].args
        assert 'calle' in sql, "Falta la columna calle en el INSERT"
        assert _param_for_column(sql, params, 'calle') == 'Av. Reforma'

    def test_post_registro_sin_calle_guarda_cadena_vacia(self, client):
        conn, cur = fake_db(fetchone_value={'valor': '1'})
        with patch('app.get_db', return_value=conn):
            r = client.post('/api/registros', json={
                'tipo': 'ENTRADA', 'fecha': '2026-07-15', 'pga': 'ESTERITO', 'origen': 'NEGOCIO'
            }, headers=AUTH)
        assert r.status_code == 201
        insert_calls = [c for c in cur.execute.call_args_list if 'INSERT INTO registros' in c.args[0]]
        sql, params = insert_calls[0].args
        assert _param_for_column(sql, params, 'calle') == ''
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_registros.py::TestCrearRegistroCalle -v`
Expected: FAIL — `ValueError: 'calle' is not in list` (the INSERT column list doesn't contain `calle` yet)

- [ ] **Step 3: Write minimal implementation**

In `app.py`, `crear_registro()` currently reads (lines 132-150):

```python
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
```

Replace with:

```python
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
                    float(d.get('m3') or 0),
                    d.get('obs', '')
                ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_registros.py::TestCrearRegistroCalle -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_registros.py
git commit -m "feat: POST /api/registros guarda el campo calle"
```

---

## Task 3: Backend — autocompletado por placa incluye `calle`

**Files:**
- Modify: `app.py:155-175` (`buscar_placa`)
- Modify: `tests/test_registros.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_registros.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_registros.py::TestBuscarPlacaCalle -v`
Expected: FAIL — `KeyError: 'calle'` (the response JSON doesn't have that key yet, since the mocked `fila` dict has it but the endpoint doesn't SELECT it — the real endpoint's `dict(row)` would only contain what's actually queried from Postgres; here the mock returns the full dict regardless, so the failure will actually show as the SQL-content assertion failing: `AssertionError: Falta calle en el SELECT de buscar-placa`)

- [ ] **Step 3: Write minimal implementation**

In `app.py`, `buscar_placa()` currently reads (lines 166-171):

```python
                cur.execute("""
                    SELECT vehiculo, detalle, origen, nombre, colonia
                    FROM registros
                    WHERE UPPER(placa) LIKE %s AND tipo='ENTRADA'
                    ORDER BY id DESC LIMIT 1
                """, (q + '%',))
```

Replace with:

```python
                cur.execute("""
                    SELECT vehiculo, detalle, origen, nombre, calle, colonia
                    FROM registros
                    WHERE UPPER(placa) LIKE %s AND tipo='ENTRADA'
                    ORDER BY id DESC LIMIT 1
                """, (q + '%',))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_registros.py -v`
Expected: PASS (both test classes)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_registros.py
git commit -m "feat: autocompletado por placa incluye calle"
```

---

## Task 4: Backend — exportación a Excel incluye "Nombre" y "Calle"

**Files:**
- Modify: `app.py:299-347` (`export_excel`)
- Create: `tests/test_export.py`

> Nota (ver spec, sección 4.3): los headers actuales de `export_excel()` ya omiten "Nombre" a pesar de que la columna existe hace varios commits — se corrige junto con "Calle" para que el Excel quede consistente con Historial.

- [ ] **Step 1: Write the failing test**

Create `tests/test_export.py`:

```python
"""
Tests para GET /api/export/excel — verifica que el reporte incluya
las columnas Nombre y Calle.
"""
import os, sys, io, base64, pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('AUTH_USER', 'usuario_test')
os.environ.setdefault('AUTH_PASS', 'clave_test')

if 'app' in sys.modules:
    del sys.modules['app']

import app as app_module
import openpyxl

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'usuario_test:clave_test').decode()}


def fake_db(fetchall_value):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = fetchall_value
    conn.cursor.return_value = cur
    return conn


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


class TestExportExcelCalle:
    def test_export_incluye_columnas_nombre_y_calle(self, client):
        fila = {
            'id': 1, 'folio': 'ENT-0001', 'tipo': 'ENTRADA', 'fecha': '2026-07-15',
            'hora': '10:00', 'pga': 'ESTERITO', 'detalle': 'ESCOMBRO', 'origen': 'NEGOCIO',
            'nombre': 'Juan Perez', 'calle': 'Av. Reforma', 'colonia': 'Centro',
            'vehiculo': 'CARROMATO', 'placa': 'ABC-123', 'm3': 2.5, 'obs': '',
            'creado_en': '2026-07-15 10:00:00'
        }
        with patch('app.get_db', return_value=fake_db([fila])):
            r = client.get('/api/export/excel', headers=AUTH)
        assert r.status_code == 200

        wb = openpyxl.load_workbook(io.BytesIO(r.data))
        ws = wb.active
        headers = [c.value for c in ws[1]]
        assert 'Nombre' in headers
        assert 'Calle' in headers

        row2 = [c.value for c in ws[2]]
        assert 'Juan Perez' in row2
        assert 'Av. Reforma' in row2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_export.py -v`
Expected: FAIL — `AssertionError: assert 'Nombre' in [...]` (current headers don't include "Nombre" or "Calle"), or a `KeyError: 'nombre'`/`'calle'` from the `row[...]` access in `export_excel()` if headers are checked first — either way, RED

- [ ] **Step 3: Write minimal implementation**

In `app.py`, `export_excel()` currently reads (lines 321-336):

```python
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
```

Replace with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite before moving to frontend**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS (auth, dashboard, init_db, registros, export)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_export.py
git commit -m "feat: exportación a Excel incluye columnas Nombre y Calle"
```

---

## Task 5: Backend (ops) — `migrate_data.py` agrega la columna en producción

**Files:**
- Modify: `migrate_data.py`

This script has no automated tests in this codebase (it's a manual one-off run against the Render production database — see its own docstring). Verification here is a syntax check plus a manual read-through, matching how the existing `nombre` migration was handled.

- [ ] **Step 1: Add the ALTER TABLE statement**

In `migrate_data.py`, right after the existing `nombre` migration (lines 47-50):

```python
            # Agregar columna nombre si la tabla ya existía sin ella
            cur.execute('''
                ALTER TABLE registros ADD COLUMN IF NOT EXISTS nombre TEXT
            ''')
```

Add:

```python
            # Agregar columna calle si la tabla ya existía sin ella
            cur.execute('''
                ALTER TABLE registros ADD COLUMN IF NOT EXISTS calle TEXT
            ''')
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -m py_compile migrate_data.py`
Expected: no output, exit code 0

- [ ] **Step 3: Commit**

```bash
git add migrate_data.py
git commit -m "feat: migrate_data.py agrega columna calle en producción"
```

> **Recordatorio para el usuario (no es parte de esta tarea automatizada):** después de desplegar este cambio a Render, correr una vez `DATABASE_URL="<external db url>" python3 migrate_data.py` para agregar la columna `calle` a la base de datos de producción — igual que se hizo para `nombre`.

---

## Task 6: Frontend — campo "Calle" en el formulario de Entrada

**Files:**
- Modify: `templates/index.html` (CSS: lines 75, 146, 160; form: lines 253-274; JS: `registrarEntrada()` ~line 627, `limpiarE()` ~line 590, `aplicarAutocompletado()` ~line 934)

No automated test — this file has no JS test suite in this codebase. Verified manually in Task 8.

- [ ] **Step 1: Add the `.cols-4` CSS class**

Line 75 currently:

```css
  .cols-3{grid-template-columns:1fr 1fr 1fr}.cols-2{grid-template-columns:1fr 1fr}
```

Change to:

```css
  .cols-3{grid-template-columns:1fr 1fr 1fr}.cols-2{grid-template-columns:1fr 1fr}.cols-4{grid-template-columns:1fr 1fr 1fr 1fr}
```

Line 146 (tablet breakpoint) currently ends with `.cols-3{grid-template-columns:1fr 1fr}}`. Change that fragment to:

```css
.cols-3{grid-template-columns:1fr 1fr}.cols-4{grid-template-columns:1fr 1fr}}
```

Line 160 currently:

```css
    .cols-2,.cols-3{grid-template-columns:1fr}
```

Change to:

```css
    .cols-2,.cols-3,.cols-4{grid-template-columns:1fr}
```

- [ ] **Step 2: Add the Calle field to the Entrada form**

In the block starting `<div class="form-grid cols-3">` right before `<div class="field"><label>Tipo de vehículo</label>` (line 253), change the wrapping class from `cols-3` to `cols-4`.

Then, the last field in that same row currently reads (line 273):

```html
          <div class="field"><label>Colonia de origen</label><input type="text" id="e-colonia" placeholder="Ej. Col. Centro..."/></div>
```

Change to:

```html
          <div class="field"><label>Calle</label><input type="text" id="e-calle" placeholder="Ej. Av. Reforma..."/></div>
          <div class="field"><label>Colonia de origen</label><input type="text" id="e-colonia" placeholder="Ej. Col. Centro..."/></div>
```

(The `<select id="e-vehiculo">` and `<select id="e-carga">` fields between them are unchanged.)

- [ ] **Step 3: Send `calle` when registering an entrada**

In `registrarEntrada()`, line 628 currently:

```javascript
        colonia: document.getElementById('e-colonia').value.trim(),
```

Change to:

```javascript
        calle: document.getElementById('e-calle').value.trim(),
        colonia: document.getElementById('e-colonia').value.trim(),
```

- [ ] **Step 4: Reset `e-calle` in `limpiarE()`**

Line 590 currently:

```javascript
  ['e-fecha','e-hora','e-origen','e-nombre','e-vehiculo','e-carga','e-colonia','e-placa','e-m3','e-obs','e-otro-txt']
```

Change to:

```javascript
  ['e-fecha','e-hora','e-origen','e-nombre','e-vehiculo','e-carga','e-calle','e-colonia','e-placa','e-m3','e-obs','e-otro-txt']
```

- [ ] **Step 5: Apply `calle` from placa autocomplete**

In `aplicarAutocompletado()`, line 934 currently:

```javascript
  if (r.colonia)  document.getElementById('e-colonia').value  = r.colonia;
```

Change to:

```javascript
  if (r.calle)    document.getElementById('e-calle').value    = r.calle;
  if (r.colonia)  document.getElementById('e-colonia').value  = r.colonia;
```

- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "feat: campo Calle en el formulario de entrada"
```

---

## Task 7: Frontend — columna "Calle" en Historial

**Files:**
- Modify: `templates/index.html` (table header ~line 439, row render ~line 844)

- [ ] **Step 1: Add the "Calle" header column**

Line 438-439 currently:

```html
              <th style="width:140px">Nombre</th>
              <th style="width:110px">Colonia</th>
```

Change to:

```html
              <th style="width:140px">Nombre</th>
              <th style="width:110px">Calle</th>
              <th style="width:110px">Colonia</th>
```

- [ ] **Step 2: Render the `calle` cell in each row**

Line 843-844 currently:

```javascript
        '<td>' + (r.nombre||'—') + '</td>' +
        '<td>' + (r.colonia||'—') + '</td>' +
```

Change to:

```javascript
        '<td>' + (r.nombre||'—') + '</td>' +
        '<td>' + (r.calle||'—') + '</td>' +
        '<td>' + (r.colonia||'—') + '</td>' +
```

(Salida rows have no `calle` — this shows `—` for them automatically, same as `nombre`/`colonia` already do.)

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: columna Calle en tabla de Historial"
```

---

## Task 8: Manual verification in browser (static, no live DB)

The app requires a real PostgreSQL `DATABASE_URL` to run end-to-end (`app.py` raises at import time otherwise), which isn't available in this environment. `templates/index.html` has no Jinja templating (verified: no `{{`/`{%` in the file) so it can be served as a static file to verify DOM structure, CSS layout, and client-side JS (`limpiarE()`, form field wiring) without a backend. API-dependent behavior (actual save, actual autocomplete fetch, actual Historial data) cannot be verified here and must be checked after deploying and running `migrate_data.py` against production.

**Files:**
- Create (temporary, not committed): `.claude/launch.json`

- [ ] **Step 1: Set up a temporary static file server for the Browser pane**

Create `.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "static-preview",
      "runtimeExecutable": "python3",
      "runtimeArgs": ["-m", "http.server", "8731", "--directory", "templates"],
      "port": 8731
    }
  ]
}
```

Start it with the `preview_start` tool (`name: "static-preview"`), then `navigate` to `http://localhost:8731/index.html`.

- [ ] **Step 2: Verify the Entrada form**

- [ ] Screenshot the Entrada page — confirm "Calle" appears as its own field between "Tipo de carga" and "Colonia de origen", in a 4-column row (desktop width)
- [ ] `resize_window` to `mobile` preset — confirm the row collapses to 1 column (via the `.cols-4` responsive rule) without visual overlap
- [ ] Type into "Calle" and "Colonia de origen", then click "Limpiar" — confirm both fields empty (verifies `limpiarE()` change without needing the backend)
- [ ] Check `read_console_messages` for JS errors on page load and after clicking Limpiar

- [ ] **Step 3: Verify the Historial table header**

- [ ] Navigate to the Historial tab — confirm the table header row shows "Nombre", "Calle", "Colonia" in that order (the table body will be empty/show the "sin conexión" state since there's no backend — that's expected here)

- [ ] **Step 4: Clean up**

```bash
rm -f .claude/launch.json
rmdir .claude 2>/dev/null || true
```

Stop the preview server with `preview_stop`.

This step intentionally has no git commit — nothing under `.claude/` should be committed; it existed only for this verification.

---

## Task 9: Full backend test suite + final review

**Files:** none (verification only)

- [ ] **Step 1: Run the complete pytest suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS — `test_auth.py`, `test_dashboard.py`, `test_init_db.py`, `test_registros.py`, `test_export.py`

- [ ] **Step 2: Sanity-check `app.py` and `migrate_data.py` syntax**

Run: `python3 -m py_compile app.py migrate_data.py`
Expected: no output, exit code 0

- [ ] **Step 3: Request code review**

Use the `superpowers:requesting-code-review` skill against the full diff for this feature before considering it done.

---

## Success Criteria (from spec)

- [ ] El formulario de Entrada muestra un campo "Calle" junto a "Colonia de origen"
- [ ] Al registrar una entrada con Calle, el dato se guarda correctamente en la base de datos
- [ ] El botón "Limpiar" también vacía el campo Calle
- [ ] Al escribir una placa ya registrada, el autocompletado sugiere también la Calle (si existía en el registro anterior)
- [ ] La tabla de Historial muestra la columna "Calle" con el valor correcto (o "—" si está vacío, incluidas las filas de Salida)
- [ ] La exportación a Excel incluye las columnas "Nombre" y "Calle" con los datos correctos
- [ ] El registro de Salida sigue funcionando sin cambios (no pide ni guarda Calle)
- [ ] El Dashboard no cambia — no aparece ninguna tarjeta o desglose nuevo relacionado con Calle
- [ ] En una base de datos ya existente en producción, correr `migrate_data.py` agrega la columna `calle` sin borrar datos existentes
- [ ] `init_db()` (desarrollo local) crea la tabla con las columnas `nombre` y `calle` incluidas, permitiendo registrar una entrada en una base local nueva sin error
