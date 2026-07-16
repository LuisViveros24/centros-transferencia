# Filtros en Historial + "Personas frecuentes" en Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-column filters to the Historial table (fixed filter row under the headers, client-side filtering) and a "Personas frecuentes" card to the Dashboard (entries grouped by normalized name, respecting the period filter).

**Architecture:** Two independent features. The Dashboard card adds one aggregate query to `/api/dashboard` (backend, TDD with pytest) plus a render block. The Historial filters are 100% client-side over the data already fetched by `renderHistorial()` — no backend change; filtered rows are simply not added to the DOM, so the existing "select all / delete selected" logic automatically only sees visible rows. `templates/index.html` has no JS test suite, so its tasks are verified manually in the browser (same approach used for the previous "Calle" feature).

**Tech Stack:** Flask, psycopg2 (PostgreSQL), vanilla JS, pytest with mocked `psycopg2` connections (see `tests/test_dashboard.py` for the established mocking pattern).

**Spec:** `docs/superpowers/specs/2026-07-16-historial-filtros-dashboard-nombres-design.md`

---

## File Map

| File | What changes |
|---|---|
| `app.py` | `dashboard()` (~lines 202-300): add the `nombres_frecuentes` aggregate query and a new key in the JSON response. No other endpoint touched. |
| `templates/index.html` | **Dashboard:** new `#nombres-frecuentes` card (~line 395) + render block in `renderDashboard()` (~line 820). **Historial:** remove `style="display:none"` from `#h-tbl` and remove `#h-empty` div (~lines 423-424); add filter `<tr>` in `<thead>`; add "Limpiar filtros" button (~line 409); new JS `_historialRows`/`_historialFiltros`/`fechaToYMD`/`fechaDisplay`/`matchesFiltroHistorial`/`aplicarFiltrosHistorial`/`_initFiltrosHistorial`/`limpiarFiltrosHistorial`; rewrite `renderHistorial()`; hook `_initFiltrosHistorial()` into the init sequence (~line 968). Small CSS for `.filtro-input`. |
| `tests/test_dashboard.py` | Add `TestNombresFrecuentes` — verifies the `nombres_frecuentes` key and the SQL semantics. |

No changes to `GET /api/registros`, `GET /api/export/excel`, the Salida form, or the "Orígenes" dashboard card.

---

## Task 1: Backend — `nombres_frecuentes` en `/api/dashboard`

**Files:**
- Modify: `app.py` (`dashboard()`, add query before the `finally`, add key in the `return jsonify(...)`)
- Modify: `tests/test_dashboard.py` (append a new test class)

- [x] **Step 1: Write the failing test**

Append to `tests/test_dashboard.py` (reuse the existing `fake_db`, `client` fixture and `AUTH` already defined in that file — do NOT redefine them, and do NOT add any `os.environ`/`sys.modules` boilerplate; `tests/conftest.py` already handles env setup):

```python
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
```

> Note on the mock: the shared `fake_db()` in `tests/test_dashboard.py` returns `cur.fetchall.return_value = []` and `cur.fetchone.return_value = {'c': 0, 'v': 0}`. The new query uses the `qa()` helper (which calls `fetchall`), so it returns `[]` → `nombres_frecuentes` is an empty list. That's why the test checks key presence + SQL text rather than specific rows (the same mock feeds every `qa()`/`q()` call in `dashboard()`, so injecting per-query rows would be brittle — inspecting the executed SQL is the robust way to verify semantics, matching how `tests/test_registros.py` verified `buscar_placa`'s SELECT).

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_dashboard.py::TestNombresFrecuentes -v`
Expected: FAIL — `AssertionError: Falta la clave nombres_frecuentes` (and the SQL test fails to find the `HAVING COUNT(*) > 3` query, since it doesn't exist yet)

- [x] **Step 3: Write minimal implementation**

In `app.py`, inside `dashboard()`, immediately after the `hist = qa("""...""", [desde, hasta])` block (currently ending at line ~288, just before the `finally:` on line ~289), add:

```python
                nombres_frecuentes = qa("""
                    SELECT
                        (ARRAY_AGG(nombre ORDER BY id DESC))[1] AS nombre,
                        COUNT(*) AS c
                    FROM registros
                    WHERE tipo='ENTRADA' AND fecha BETWEEN %s AND %s
                      AND nombre IS NOT NULL AND TRIM(nombre) != ''
                    GROUP BY LOWER(TRIM(nombre))
                    HAVING COUNT(*) > 3
                    ORDER BY c DESC
                """, [desde, hasta])
```

Then, in the `return jsonify({...})` dict (currently lines ~292-300), add a new key after `'origen_counts': origen_counts,`:

```python
        'origen_counts': origen_counts,
        'nombres_frecuentes': [{'nombre': r['nombre'], 'count': r['c']} for r in nombres_frecuentes],
        'historial': [dict(r) for r in hist]
```

(The `'historial'` line already exists — just insert the `'nombres_frecuentes'` line before it.)

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_dashboard.py::TestNombresFrecuentes -v`
Expected: PASS (both tests)

- [x] **Step 5: Run the full suite to confirm no regression**

Run: `python3 -m pytest tests/ -v`
Expected: all tests PASS (the 20 existing + 2 new = 22)

- [x] **Step 6: Commit**

```bash
git add app.py tests/test_dashboard.py
git commit -m "feat: dashboard — consulta de personas frecuentes por nombre normalizado"
```

---

## Task 2: Frontend — tarjeta "Personas frecuentes" en Dashboard

**Files:**
- Modify: `templates/index.html` (HTML card ~line 395; render block in `renderDashboard()` ~line 820)

No JS test suite — verified manually in Task 5. This task builds directly on Task 1's `nombres_frecuentes` JSON field.

- [x] **Step 1: Add the card HTML**

In `templates/index.html`, the "Orígenes" card currently reads (lines ~392-395):

```html
      <div class="card">
        <div class="card-label">Orígenes (acumulado total)</div>
        <div id="origen-counts" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:4px"></div>
      </div>
```

Immediately **after** that closing `</div>` (the card's closing div), insert a new card:

```html
      <div class="card">
        <div class="card-label">Personas frecuentes (más de 3 entradas en el periodo)</div>
        <div id="nombres-frecuentes" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:4px"></div>
      </div>
```

- [x] **Step 2: Add the render block**

In `renderDashboard()`, the origen-counts render currently ends like this (lines ~809-820):

```javascript
    // Origen counts
    const total = d.origen_counts.reduce((s,o) => s+o.count, 0);
    document.getElementById('origen-counts').innerHTML = d.origen_counts.length
      ? d.origen_counts.map(o => {
          const pct = total ? Math.round(o.count/total*100) : 0;
          return '<div style="background:var(--bg2);border-radius:var(--radius);padding:12px 14px;">' +
            '<div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em">' + o.origen + '</div>' +
            '<div style="font-size:24px;font-weight:700;color:var(--text);line-height:1">' + o.count + '</div>' +
            '<div style="font-size:11px;color:var(--text3);margin-top:4px">' + pct + '% del total</div>' +
            '</div>';
        }).join('')
      : '<div style="font-size:13px;color:var(--text2);padding:8px 0">Sin registros de entradas aún.</div>';
```

Immediately **after** that statement (after its closing `;`), add the analogous block for `nombres_frecuentes`:

```javascript
    // Personas frecuentes (nombre)
    document.getElementById('nombres-frecuentes').innerHTML = d.nombres_frecuentes.length
      ? d.nombres_frecuentes.map(n =>
          '<div style="background:var(--bg2);border-radius:var(--radius);padding:12px 14px;">' +
            '<div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em">' + n.nombre + '</div>' +
            '<div style="font-size:24px;font-weight:700;color:var(--text);line-height:1">' + n.count + '</div>' +
            '<div style="font-size:11px;color:var(--text3);margin-top:4px">entradas</div>' +
          '</div>'
        ).join('')
      : '<div style="font-size:13px;color:var(--text2);padding:8px 0">Nadie superó 3 entradas en este periodo.</div>';
```

- [x] **Step 3: Sanity check**

Run: `python3 -c "c=open('templates/index.html').read(); assert c.count('id=\"nombres-frecuentes\"')==1; assert 'd.nombres_frecuentes' in c; print('OK')"`
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: dashboard — tarjeta de personas frecuentes"
```

---

## Task 3: Frontend — refactor de Historial (guardar filas, filtrar, estado vacío, formato de fecha)

**Files:**
- Modify: `templates/index.html` (HTML `#h-tbl`/`#h-empty` ~lines 423-424; JS `renderHistorial()` and helpers ~lines 827-860)

This task does the JS plumbing **without adding the filter UI yet**. After it, the table still shows all rows (filters are all-empty), but: dates render as `DD/MM/YYYY`, the count/empty-state logic goes through the new code path, and the table no longer hides itself. The filter UI comes in Task 4. No JS test suite — verified manually here and in Task 5.

- [x] **Step 1: Remove the always-hidden table attribute and the separate empty-state div**

In `templates/index.html`, the Historial table currently starts like this (lines ~423-424):

```html
          <div class="empty-state" id="h-empty">No hay registros aún.</div>
          <table id="h-tbl" style="display:none">
```

Change to (delete the `#h-empty` div entirely, and remove `style="display:none"` from the table — the empty state is now a row inside `#h-body`):

```html
          <table id="h-tbl">
```

- [x] **Step 2: Add the `fechaToYMD` and `fechaDisplay` helpers**

In `templates/index.html`, just above the `// ── Historial ──` comment (currently ~line 827), add:

```javascript
// ── Fecha: normalización y formato ─────────────────────────────
// r.fecha llega como string HTTP ("Thu, 16 Jul 2026 00:00:00 GMT"), no ISO.
// Se usan getters UTC a propósito: fecha es una columna DATE sin hora, así que
// "00:00:00 GMT" es solo artefacto de serialización — convertir con getters
// locales correría la fecha un día hacia atrás en UTC-6.
function fechaToYMD(rawFecha) {
  const d = new Date(rawFecha);
  return d.getUTCFullYear() + '-' + String(d.getUTCMonth()+1).padStart(2,'0') + '-' + String(d.getUTCDate()).padStart(2,'0');
}
function fechaDisplay(rawFecha) {
  const [y, m, d] = fechaToYMD(rawFecha).split('-');
  return d + '/' + m + '/' + y;
}
```

- [x] **Step 3: Add module state and the filter/apply functions; rewrite `renderHistorial()`**

The current `renderHistorial()` (lines ~828-860) reads:

```javascript
async function renderHistorial() {
  try {
    const rows = await api('/api/registros');
    const empty = document.getElementById('h-empty');
    const tbl   = document.getElementById('h-tbl');
    document.getElementById('h-count').textContent = rows.length + (rows.length===1?' registro':' registros');
    if (!rows.length) { empty.style.display=''; tbl.style.display='none'; return; }
    empty.style.display='none'; tbl.style.display='';
    document.getElementById('h-body').innerHTML = rows.map(r =>
      '<tr>' +
        '<td style="text-align:center"><input type="checkbox" value="' + r.id + '" onchange="actualizarBarraAccion()"/></td>' +
        '<td class="mono">' + r.id + '</td>' +
        '<td class="mono">' + r.folio + '</td>' +
        '<td><span class="badge ' + (r.tipo==='ENTRADA'?'badge-in':'badge-out') + '">' + (r.tipo==='ENTRADA'?'ENT':'SAL') + '</span></td>' +
        '<td>' + r.fecha + '</td>' +
        '<td>' + (r.hora||'—') + '</td>' +
        '<td style="font-weight:600">' + r.pga + '</td>' +
        '<td>' + (r.detalle||'—') + '</td>' +
        '<td>' + (r.origen||'—') + '</td>' +
        '<td>' + (r.nombre||'—') + '</td>' +
        '<td>' + (r.calle||'—') + '</td>' +
        '<td>' + (r.colonia||'—') + '</td>' +
        '<td>' + (r.placa||'—') + '</td>' +
        '<td>' + (r.m3 ? parseFloat(r.m3).toFixed(2) : '—') + '</td>' +
        '<td style="max-width:200px;color:var(--text2)">' + (r.obs||'—') + '</td>' +
      '</tr>'
    ).join('');
  } catch(e) {
    toast('Error al cargar el historial.');
  } finally {
    actualizarBarraAccion();
  }
}
```

Replace that entire function with the following (new state + `matchesFiltroHistorial` + `aplicarFiltrosHistorial` + a slimmed `renderHistorial`). Note the Fecha cell now uses `fechaDisplay(r.fecha)`:

```javascript
// ── Historial: estado de filtros ───────────────────────────────
let _historialRows = [];
let _historialFiltros = { folio:'', tipo:'', fecha:'', pga:'', origen:'', nombre:'', calle:'', colonia:'', placa:'', obs:'' };

function matchesFiltroHistorial(r) {
  const f = _historialFiltros;
  const contiene = (val, filtro) => !filtro || String(val||'').toLowerCase().includes(filtro.toLowerCase());
  const igual    = (val, filtro) => !filtro || String(val||'') === filtro;
  if (!contiene(r.folio,   f.folio))   return false;
  if (!igual(r.tipo,       f.tipo))    return false;
  if (f.fecha && fechaToYMD(r.fecha) !== f.fecha) return false;
  if (!igual(r.pga,        f.pga))     return false;
  if (!igual(r.origen,     f.origen))  return false;
  if (!contiene(r.nombre,  f.nombre))  return false;
  if (!contiene(r.calle,   f.calle))   return false;
  if (!contiene(r.colonia, f.colonia)) return false;
  if (!contiene(r.placa,   f.placa))   return false;
  if (!contiene(r.obs,     f.obs))     return false;
  return true;
}

function filaHistorial(r) {
  return '<tr>' +
    '<td style="text-align:center"><input type="checkbox" value="' + r.id + '" onchange="actualizarBarraAccion()"/></td>' +
    '<td class="mono">' + r.id + '</td>' +
    '<td class="mono">' + r.folio + '</td>' +
    '<td><span class="badge ' + (r.tipo==='ENTRADA'?'badge-in':'badge-out') + '">' + (r.tipo==='ENTRADA'?'ENT':'SAL') + '</span></td>' +
    '<td>' + fechaDisplay(r.fecha) + '</td>' +
    '<td>' + (r.hora||'—') + '</td>' +
    '<td style="font-weight:600">' + r.pga + '</td>' +
    '<td>' + (r.detalle||'—') + '</td>' +
    '<td>' + (r.origen||'—') + '</td>' +
    '<td>' + (r.nombre||'—') + '</td>' +
    '<td>' + (r.calle||'—') + '</td>' +
    '<td>' + (r.colonia||'—') + '</td>' +
    '<td>' + (r.placa||'—') + '</td>' +
    '<td>' + (r.m3 ? parseFloat(r.m3).toFixed(2) : '—') + '</td>' +
    '<td style="max-width:200px;color:var(--text2)">' + (r.obs||'—') + '</td>' +
  '</tr>';
}

function aplicarFiltrosHistorial() {
  const body = document.getElementById('h-body');
  const filtered = _historialRows.filter(matchesFiltroHistorial);
  document.getElementById('h-count').textContent = filtered.length + (filtered.length===1?' registro':' registros');

  if (!filtered.length) {
    const hayFiltro = Object.values(_historialFiltros).some(v => v);
    const msg = (!hayFiltro && _historialRows.length === 0)
      ? 'No hay registros aún.'
      : 'Ningún registro coincide con los filtros.';
    body.innerHTML = '<tr><td colspan="15" style="text-align:center;color:var(--text2);padding:20px">' + msg + '</td></tr>';
  } else {
    body.innerHTML = filtered.map(filaHistorial).join('');
  }

  // El conjunto visible cambió: limpiar selección para no arrastrar checks ocultos.
  const master = document.querySelector('#h-tbl thead input[type=checkbox]');
  if (master) master.checked = false;
  actualizarBarraAccion();
}

// ── Historial ──────────────────────────────────────────────────
async function renderHistorial() {
  try {
    _historialRows = await api('/api/registros');
    aplicarFiltrosHistorial();
  } catch(e) {
    toast('Error al cargar el historial.');
  }
}
```

> The `actualizarBarraAccion`, `toggleTodos`, and `eliminarSeleccionados` functions right below this (lines ~862-902) are **unchanged** — they keep operating on `#h-body input[type=checkbox]`, which now only ever contains visible rows.

- [x] **Step 4: Sanity check**

Run: `python3 -c "c=open('templates/index.html').read(); assert 'style=\"display:none\">' not in c.split('id=\"h-tbl\"')[1][:40]; assert 'id=\"h-empty\"' not in c; assert 'fechaDisplay(r.fecha)' in c; assert c.count('function aplicarFiltrosHistorial')==1; print('OK')"`
Expected: `OK`

- [x] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "refactor: historial — guardar filas y filtrar en cliente, fecha DD/MM/YYYY"
```

---

## Task 4: Frontend — fila de filtros, wiring y botón "Limpiar filtros"

**Files:**
- Modify: `templates/index.html` (CSS `.filtro-input` ~line 123 area; filter `<tr>` in `<thead>` ~line 441; "Limpiar filtros" button ~line 409; init hook ~line 968; new `_initFiltrosHistorial`/`limpiarFiltrosHistorial` JS)

Builds on Task 3. Adds the visible filter controls and wires them to `_historialFiltros` + `aplicarFiltrosHistorial()`. No JS test suite — verified manually in Task 5.

- [x] **Step 1: Add compact CSS for the filter inputs**

In `templates/index.html`, right after the `thead th{...}` rule (line ~123), add:

```css
  thead tr.filtros-row th{padding:6px 8px;background:var(--bg2)}
  .filtro-input{padding:4px 6px;font-size:12px;text-transform:none;letter-spacing:normal;font-weight:400}
```

- [x] **Step 2: Add the filter row to the table header**

The header row currently ends like this (lines ~440-441):

```html
              <th>Observaciones</th>
            </tr></thead>
```

Change to (add a second `<tr class="filtros-row">` after the header `</tr>`, still inside `<thead>` — 15 cells matching the 15 columns; empty `<th>` for columns without a filter):

```html
              <th>Observaciones</th>
            </tr>
            <tr class="filtros-row">
              <th></th>
              <th></th>
              <th><input type="text" class="filtro-input" data-filtro="folio" placeholder="Filtrar"/></th>
              <th><select class="filtro-input" data-filtro="tipo"><option value="">Todos</option><option>ENTRADA</option><option>SALIDA</option></select></th>
              <th><input type="date" class="filtro-input" data-filtro="fecha"/></th>
              <th></th>
              <th><select class="filtro-input" data-filtro="pga" id="filtro-pga"><option value="">Todos</option></select></th>
              <th></th>
              <th><select class="filtro-input" data-filtro="origen"><option value="">Todos</option><option>NEGOCIO</option><option>RECOLECTORES</option><option>CASA-HABITACIÓN</option><option>CEA</option><option>LA OLA</option><option>CONTRATISTAS</option></select></th>
              <th><input type="text" class="filtro-input" data-filtro="nombre" placeholder="Filtrar"/></th>
              <th><input type="text" class="filtro-input" data-filtro="calle" placeholder="Filtrar"/></th>
              <th><input type="text" class="filtro-input" data-filtro="colonia" placeholder="Filtrar"/></th>
              <th><input type="text" class="filtro-input" data-filtro="placa" placeholder="Filtrar"/></th>
              <th></th>
              <th><input type="text" class="filtro-input" data-filtro="obs" placeholder="Filtrar"/></th>
            </tr></thead>
```

> The PGA `<select>` is intentionally left with only the "Todos" option here — its values are filled from the existing `PGAS` constant in Step 4, per the spec (no second hardcoded copy of the PGA list). Origen has no such constant, so its 6 values are hardcoded (same list already hardcoded in the entry form).

- [x] **Step 3: Add the "Limpiar filtros" button**

In `.table-actions` (lines ~407-410), currently:

```html
        <div class="table-actions">
          <span class="count-pill" id="h-count">0 registros</span>
          <button class="btn btn-ghost" onclick="exportarExcel()">Exportar Excel</button>
        </div>
```

Change to (add the button before "Exportar Excel"):

```html
        <div class="table-actions">
          <span class="count-pill" id="h-count">0 registros</span>
          <button class="btn btn-ghost" onclick="limpiarFiltrosHistorial()">Limpiar filtros</button>
          <button class="btn btn-ghost" onclick="exportarExcel()">Exportar Excel</button>
        </div>
```

- [x] **Step 4: Add `_initFiltrosHistorial` and `limpiarFiltrosHistorial`**

In `templates/index.html`, add these functions right after `aplicarFiltrosHistorial()` (from Task 3), before the `// ── Historial ──` comment:

```javascript
let _filtroTimer = null;
function _initFiltrosHistorial() {
  const pgaSel = document.getElementById('filtro-pga');
  pgaSel.innerHTML = '<option value="">Todos</option>' + PGAS.map(p => '<option>' + p + '</option>').join('');
  document.querySelectorAll('.filtro-input').forEach(el => {
    const evt = (el.tagName === 'SELECT' || el.type === 'date') ? 'change' : 'input';
    el.addEventListener(evt, () => {
      _historialFiltros[el.dataset.filtro] = el.value;
      if (evt === 'input') {
        clearTimeout(_filtroTimer);
        _filtroTimer = setTimeout(aplicarFiltrosHistorial, 250);
      } else {
        aplicarFiltrosHistorial();
      }
    });
  });
}

function limpiarFiltrosHistorial() {
  document.querySelectorAll('.filtro-input').forEach(el => el.value = '');
  Object.keys(_historialFiltros).forEach(k => _historialFiltros[k] = '');
  aplicarFiltrosHistorial();
}
```

- [x] **Step 5: Hook the init into the load sequence**

At the bottom `// ── Init ──` block (lines ~962-968), after `_initPlacaHint();` (line ~968), add:

```javascript
_initPlacaHint();
_initFiltrosHistorial();
```

- [x] **Step 6: Sanity check**

Run: `python3 -c "c=open('templates/index.html').read(); assert c.count('class=\"filtros-row\"')==1; assert c.count('data-filtro=')==10; assert 'function _initFiltrosHistorial' in c; assert '_initFiltrosHistorial();' in c; assert 'onclick=\"limpiarFiltrosHistorial()\"' in c; print('OK')"`
Expected: `OK` (10 filter controls: folio, tipo, fecha, pga, origen, nombre, calle, colonia, placa, obs)

- [x] **Step 7: Commit**

```bash
git add templates/index.html
git commit -m "feat: historial — fila de filtros por columna y botón limpiar"
```

---

## Task 5: Verificación manual en navegador (estático) + suite backend

`templates/index.html` has no Jinja templating (pure static HTML/CSS/JS), so it can be served as a static file to verify DOM structure, filtering behavior, and rendering without a backend. API-dependent behavior (real data in the table, real dashboard numbers) can't be exercised here — the table will show the "Error al cargar el historial" / empty state — but the filter row markup, the date helpers, the filter logic against injected fake rows, and the dashboard card markup **can** be verified via the browser's JS console.

**Files:**
- Create (temporary, NOT committed): `.claude/launch.json`

- [x] **Step 1: Start a static file server for the Browser pane**

Create `.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "static-preview",
      "runtimeExecutable": "python3",
      "runtimeArgs": ["-m", "http.server", "8734", "--directory", "templates"],
      "port": 8734
    }
  ]
}
```

Start it with `preview_start` (`name: "static-preview"`), then `navigate` to `http://localhost:8734/index.html`.

- [x] **Step 2: Verify the Historial filter row (structure + logic)**

- [x] Navigate to the Historial tab. Confirm a second row of filter controls appears under the headers: text inputs under Folio/Nombre/Calle/Colonia/Placa/Observaciones, dropdowns under Tipo/PGA/Origen, a date picker under Fecha, and empty cells under the checkbox/ID/Hora/Detalle/m³ columns.
- [x] Confirm the PGA dropdown lists the 5 PGAs (ROVIROSA WADE, LEY SAULO, ESTERITO, RECOVERDE, COMPRESORA) plus "Todos".
- [x] Inject fake rows and verify filtering via the console (use `javascript_tool`):
  ```javascript
  _historialRows = [
    {id:1, folio:'ENT-7119', tipo:'ENTRADA', fecha:'Thu, 16 Jul 2026 00:00:00 GMT', hora:'10:54', pga:'LEY SAULO', detalle:'ESCOMBRO', origen:'CASA-HABITACIÓN', nombre:'Antonio Gómez', calle:'', colonia:'Las fuentes', placa:'CTVM005', m3:1, obs:''},
    {id:2, folio:'SAL-7118', tipo:'SALIDA', fecha:'Thu, 16 Jul 2026 00:00:00 GMT', hora:'10:52', pga:'ROVIROSA WADE', detalle:'VOLTEO GRANDE', origen:'', nombre:'', calle:'', colonia:'VOLTEO GRANDE', placa:'8-FBB-35A', m3:14, obs:'Camión con lona'}
  ];
  aplicarFiltrosHistorial();
  ```
  Then confirm:
  - [ ] Both rows render; the Fecha cell shows `16/07/2026` (DD/MM/YYYY), not the raw GMT string.
  - [ ] Set `_historialFiltros.tipo='ENTRADA'; aplicarFiltrosHistorial();` → only the ENTRADA row shows; count pill reads "1 registro".
  - [ ] Set `_historialFiltros.tipo=''; _historialFiltros.nombre='antonio'; aplicarFiltrosHistorial();` → only Antonio's row shows (case-insensitive partial match works).
  - [ ] Set `_historialFiltros.nombre='xyz'; aplicarFiltrosHistorial();` → table shows the row "Ningún registro coincide con los filtros." AND the filter row is still visible above it.
  - [ ] Type a value into a real text filter input in the UI, then click "Limpiar filtros" → all filter inputs clear and all rows return.
- [x] Check `read_console_messages` for JS errors after these interactions.

- [x] **Step 3: Verify the Dashboard card (structure)**

- [x] Navigate to the Dashboard tab. Confirm a "Personas frecuentes (más de 3 entradas en el periodo)" card appears (it will be empty / show its fallback since there's no backend). Inject a render to confirm the template:
  ```javascript
  document.getElementById('nombres-frecuentes').innerHTML = '';
  var d = {nombres_frecuentes:[{nombre:'Antonio Gómez', count:7},{nombre:'Benito Ibarra', count:5}]};
  document.getElementById('nombres-frecuentes').innerHTML = d.nombres_frecuentes.map(n => '<div style="background:var(--bg2);border-radius:8px;padding:12px 14px"><div style="font-size:11px">'+n.nombre+'</div><div style="font-size:24px;font-weight:700">'+n.count+'</div><div style="font-size:11px">entradas</div></div>').join('');
  ```
  Confirm two cards render with name + count + "entradas".

- [x] **Step 4: Clean up**

```bash
rm -f .claude/launch.json
rmdir .claude 2>/dev/null || true
```

Stop the preview server with `preview_stop`. No commit — nothing under `.claude/` is committed.

- [x] **Step 5: Final backend suite + syntax check**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS (22 tests)

Run: `python3 -m py_compile app.py`
Expected: no output, exit 0

- [x] **Step 6: Request code review**

Use the `superpowers:requesting-code-review` skill against the full diff for this feature before considering it done.

---

## Criterios de éxito (del spec)

**Historial:**
- [x] La tabla muestra una fila de filtros fija debajo de los encabezados
- [x] Tipo/PGA/Origen usan dropdown con los valores conocidos
- [x] Fecha usa selector de fecha y coincide con el día exacto (sin desfase de zona horaria)
- [x] Folio/Nombre/Calle/Colonia/Placa/Observaciones buscan coincidencia parcial, sin distinguir mayúsculas/minúsculas
- [x] Combinar dos o más filtros aplica todos a la vez (Y lógico)
- [x] "Seleccionar todos" / "Eliminar seleccionados" solo afectan filas visibles
- [x] Cambiar un filtro limpia la selección previa
- [x] "Limpiar filtros" vacía los 10 campos de un clic
- [x] El pill de conteo refleja el conjunto filtrado, no el total
- [x] Con 0 coincidencias, el mensaje dice "Ningún registro coincide con los filtros."
- [x] La fila de filtros sigue visible aunque el filtro no encuentre nada
- [x] La columna Fecha se muestra como DD/MM/YYYY
- [x] La exportación a Excel sigue exportando todos los registros

**Dashboard:**
- [x] Aparece la tarjeta "Personas frecuentes" junto a "Orígenes"
- [x] Solo cuenta ENTRADA
- [x] Solo muestra personas con más de 3 entradas en el periodo seleccionado
- [x] Cambiar el periodo actualiza la tarjeta
- [x] "Antonio Gómez" y "antonio gomez " cuentan como la misma persona
- [x] Nombres vacíos nunca aparecen
- [x] Si nadie supera el umbral, se muestra un mensaje explicativo
