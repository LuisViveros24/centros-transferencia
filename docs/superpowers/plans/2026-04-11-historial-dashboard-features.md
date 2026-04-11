# Historial Bulk Delete + Dashboard Date Range — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add checkbox-based bulk delete to the Historial table and a date-range filter bar to the Dashboard, replacing the hardcoded "today" and "14-day" views.

**Architecture:** Two files only — `app.py` (backend: swap `fecha` param for `desde`/`hasta` in `/api/dashboard`, rename JSON fields) and `templates/index.html` (frontend: filter bar HTML, quick-button JS, updated `renderDashboard()`, rewritten historial chart, checkbox column + action bar for Historial). The `DELETE /api/registros/<id>` endpoint already exists and needs no changes.

**Tech Stack:** Flask, psycopg2, vanilla JS, Chart.js 4.4.1 (already loaded via CDN).

---

## File Map

| File | What changes |
|---|---|
| `app.py` | `dashboard()` function only (lines 168–240): swap `fecha`→`desde`/`hasta`, BETWEEN in all period queries, rename Python vars and JSON keys |
| `templates/index.html` | (1) JS helpers `dateToLocalStr`, `parseDateLocal`, fixed `todayStr`, new `setRapido`; (2) updated `renderDashboard()` — new params, new field names, rewritten historial chart; (3) updated `goTo()` for dashboard init; (4) filter bar HTML + metric/card label text; (5) action bar HTML + checkbox `<th>` in Historial; (6) updated `renderHistorial()` with checkbox `<td>`; (7) new functions `actualizarBarraAccion`, `toggleTodos`, `eliminarSeleccionados` |
| `tests/test_dashboard.py` | New file — 4 unit tests for new dashboard JSON shape |

---

## Task 1: Backend — Update `/api/dashboard` endpoint

**Files:**
- Modify: `app.py` lines 168–240
- Create: `tests/test_dashboard.py`

### Step 1 — Write failing tests

- [ ] Create `tests/test_dashboard.py` with this content:

```python
"""
Tests para el endpoint /api/dashboard con parámetros desde/hasta
y campos JSON renombrados.
"""
import os, sys, base64, pytest

os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('AUTH_USER', 'usuario_test')
os.environ.setdefault('AUTH_PASS', 'clave_test')

if 'app' in sys.modules:
    del sys.modules['app']

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
```

### Step 2 — Run tests to verify they fail

- [ ] Run: `cd /Users/viverosmunoz/Desktop/Sistemas\ de\ Reportes/ct_app_mac && python3 -m pytest tests/test_dashboard.py -v`
- [ ] Expected: 4 tests **FAIL** (`KeyError` o `AssertionError` porque el endpoint aún devuelve `ent_hoy`)

### Step 3 — Update `app.py`: replace `dashboard()` function

- [ ] In `app.py`, replace the entire `dashboard()` function (lines 168–240) with:

```python
@app.route('/api/dashboard', methods=['GET'])
@requiere_auth
def dashboard():
    desde = request.args.get('desde', str(date.today()))
    hasta  = request.args.get('hasta',  str(date.today()))
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
```

### Step 4 — Run all tests to verify they pass

- [ ] Run: `python3 -m pytest tests/ -v`
- [ ] Expected: **all tests pass** (8 auth tests + 4 dashboard tests = 12 total)
- [ ] If any auth test fails: it means `todayStr()` or mock issue — re-check the mock in `test_auth.py` hasn't changed

### Step 5 — Commit

- [ ] Run:
```bash
git add app.py tests/test_dashboard.py
git commit -m "feat: dashboard acepta desde/hasta, renombra campos JSON a _periodo"
```

---

## Task 2: Frontend — Dashboard filter bar + updated renderDashboard()

**Files:**
- Modify: `templates/index.html`

This task changes the JavaScript and HTML for the Dashboard page. No new test files — the backend tests already cover the API shape, and the JS is tested manually in the browser.

### Step 1 — Fix `todayStr()` and add date helper functions

- [ ] In `index.html`, find line 452:
```javascript
function todayStr() { return new Date().toISOString().split('T')[0]; }
```
Replace it with:
```javascript
// Convierte Date a string YYYY-MM-DD en hora LOCAL (no UTC, evita bug en UTC-6)
function dateToLocalStr(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}
function todayStr() { return dateToLocalStr(new Date()); }

// Parsea string YYYY-MM-DD a Date en hora local (no UTC — evita desfase de zona horaria)
function parseDateLocal(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

// Rellena los inputs d-desde / d-hasta y llama renderDashboard()
function setRapido(tipo) {
  const hoy = new Date();
  let desde, hasta;

  if (tipo === 'hoy') {
    desde = hasta = todayStr();

  } else if (tipo === 'semana') {
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - ((hoy.getDay() + 6) % 7));
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    desde = dateToLocalStr(lunes);
    hasta  = dateToLocalStr(domingo);

  } else if (tipo === 'mes') {
    desde = hoy.getFullYear() + '-' +
            String(hoy.getMonth() + 1).padStart(2, '0') + '-01';
    const ultimo = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0);
    hasta = dateToLocalStr(ultimo);
  }

  document.getElementById('d-desde').value = desde;
  document.getElementById('d-hasta').value  = hasta;
  renderDashboard();
}
```

### Step 2 — Update `goTo()` to initialize dashboard on first visit

- [ ] In `index.html`, find lines 424–427:
```javascript
function goTo(page, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  if (btn) btn.classList.add('active');
  if (page === 'dashboard') renderDashboard();
  if (page === 'historial') renderHistorial();
}
```
Replace with:
```javascript
function goTo(page, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  if (btn) btn.classList.add('active');
  if (page === 'dashboard') {
    // Primera visita: inputs vacíos → inicializar con Hoy
    if (!document.getElementById('d-desde').value) setRapido('hoy');
    else renderDashboard();
  }
  if (page === 'historial') renderHistorial();
}
```

### Step 3 — Replace `renderDashboard()` function

- [ ] In `index.html`, find the entire `renderDashboard()` function (lines 564–676):
```javascript
// ── Dashboard ──────────────────────────────────────────────
async function renderDashboard() {
  try {
    const d = await api('/api/dashboard?fecha=' + todayStr());
```
Replace the **entire function** (from `// ── Dashboard` comment through the closing `}` at line 676) with:

```javascript
// ── Dashboard ──────────────────────────────────────────────
async function renderDashboard() {
  try {
    const desde = document.getElementById('d-desde').value || todayStr();
    const hasta  = document.getElementById('d-hasta').value  || todayStr();
    const d = await api('/api/dashboard?desde=' + desde + '&hasta=' + hasta);

    document.getElementById('d-ent').textContent    = d.ent_periodo;
    document.getElementById('d-sal').textContent    = d.sal_periodo;
    document.getElementById('d-bal').textContent    = d.balance;
    document.getElementById('d-tot').textContent    = d.total;
    document.getElementById('d-m3-eh').textContent  = d.m3_ent_periodo.toFixed(2);
    document.getElementById('d-m3-sh').textContent  = d.m3_sal_periodo.toFixed(2);
    document.getElementById('d-m3-et').textContent  = d.m3_ent_tot.toFixed(2);
    document.getElementById('d-m3-st').textContent  = d.m3_sal_tot.toFixed(2);

    // PGA flow (viajes)
    document.getElementById('pga-flow').innerHTML = d.pga_flow.map(p =>
      '<div class="pga-flow-card">' +
        '<div class="pga-flow-name">' + p.pga + '</div>' +
        '<div class="pga-flow-nums">' +
          '<span class="num-in">' + p.ent + '</span>' +
          '<span class="num-sep">/</span>' +
          '<span class="num-out">' + p.sal + '</span>' +
        '</div>' +
        '<div class="pga-flow-sub">ent / sal</div>' +
      '</div>'
    ).join('');

    // PGA flow (m3)
    document.getElementById('pga-flow-m3').innerHTML = d.pga_flow.map(p =>
      '<div class="pga-flow-card">' +
        '<div class="pga-flow-name">' + p.pga + '</div>' +
        '<div class="pga-flow-nums">' +
          '<span class="num-in" style="font-size:16px">' + p.m3_ent.toFixed(1) + '</span>' +
          '<span class="num-sep">/</span>' +
          '<span class="num-out" style="font-size:16px">' + p.m3_sal.toFixed(1) + '</span>' +
        '</div>' +
        '<div class="pga-flow-sub">m3 ent / sal</div>' +
      '</div>'
    ).join('');

    const labels = d.pga_flow.map(p => p.pga.length > 9 ? p.pga.slice(0,9)+'...' : p.pga);

    // Chart viajes PGA
    if (chPga) chPga.destroy();
    chPga = new Chart(document.getElementById('ch-pga'), {
      type: 'bar',
      data: { labels, datasets: [
        { label:'Entradas', data: d.pga_flow.map(p=>p.ent), backgroundColor:'#1a6fc4', borderRadius:5, borderSkipped:false },
        { label:'Salidas',  data: d.pga_flow.map(p=>p.sal), backgroundColor:'#0f7a54', borderRadius:5, borderSkipped:false }
      ]},
      options: { responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{ display:false }},
        scales:{ y:{ ticks:{ stepSize:1 }, beginAtZero:true, grid:{ color:'rgba(128,128,128,.08)' }},
                 x:{ ticks:{ font:{ size:11 }}, grid:{ display:false }}}}
    });

    // Chart m3 PGA
    if (chM3Pga) chM3Pga.destroy();
    chM3Pga = new Chart(document.getElementById('ch-m3-pga'), {
      type: 'bar',
      data: { labels, datasets: [
        { label:'m3 entrada', data: d.pga_flow.map(p=>p.m3_ent), backgroundColor:'#1a6fc4', borderRadius:5, borderSkipped:false },
        { label:'m3 salida',  data: d.pga_flow.map(p=>p.m3_sal), backgroundColor:'#0f7a54', borderRadius:5, borderSkipped:false }
      ]},
      options: { responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{ display:false },
          tooltip:{ callbacks:{ label: function(c){ return c.dataset.label+': '+c.parsed.y.toFixed(2)+' m3'; }}}},
        scales:{ y:{ beginAtZero:true, grid:{ color:'rgba(128,128,128,.08)' },
                     ticks:{ callback: function(v){ return v+' m3'; }}},
                 x:{ ticks:{ font:{ size:11 }}, grid:{ display:false }}}}
    });

    // Chart historial — eje X dinámico desde el rango seleccionado
    const histMap = {};
    d.historial.forEach(h => {
      const key = typeof h.fecha === 'string' ? h.fecha.slice(0, 10) : h.fecha;
      histMap[key] = h;
    });

    const allDays = [];
    const cur = parseDateLocal(desde);
    const end = parseDateLocal(hasta);
    while (cur <= end) {
      allDays.push(dateToLocalStr(cur));
      cur.setDate(cur.getDate() + 1);
    }

    const dayLabels = allDays.map(dd => { const p = dd.split('-'); return p[2] + '/' + p[1]; });
    const entByDay  = allDays.map(dd => histMap[dd] ? Number(histMap[dd].entradas) : 0);
    const salByDay  = allDays.map(dd => histMap[dd] ? Number(histMap[dd].salidas)  : 0);

    if (chHist) chHist.destroy();
    chHist = new Chart(document.getElementById('ch-hist'), {
      type: 'bar',
      data: { labels: dayLabels, datasets: [
        { label:'Entradas', data: entByDay, backgroundColor:'#1a6fc4', borderRadius:4, borderSkipped:false },
        { label:'Salidas',  data: salByDay, backgroundColor:'#0f7a54', borderRadius:4, borderSkipped:false }
      ]},
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { ticks: { stepSize: 1 }, beginAtZero: true, grid: { color: 'rgba(128,128,128,.08)' } },
          x: { ticks: { font: { size: 11 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 31 },
               grid: { display: false } }
        }
      }
    });

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

  } catch(e) {
    toast('Error al cargar el dashboard.');
  }
}
```

### Step 4 — Update Dashboard HTML: add filter bar and update labels

- [ ] In `index.html`, find lines 298–300:
```html
    <!-- DASHBOARD -->
    <div id="page-dashboard" class="page">
      <div class="page-title">Dashboard</div>
      <div class="page-sub">Flujo de viajes de hoy vs histórico por PGA.</div>

      <div class="metrics-grid">
```
Replace with:
```html
    <!-- DASHBOARD -->
    <div id="page-dashboard" class="page">
      <div class="page-title">Dashboard</div>
      <div class="page-sub">Flujo de viajes por PGA en el periodo seleccionado.</div>

      <!-- Barra de filtros -->
      <div class="card" style="margin-bottom:16px;padding:14px 18px">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-size:11px;color:var(--text2);font-weight:600;text-transform:uppercase;letter-spacing:.05em">Periodo:</span>
          <button class="btn btn-ghost" style="padding:5px 12px;border-radius:20px;font-size:12px" onclick="setRapido('hoy')">Hoy</button>
          <button class="btn btn-ghost" style="padding:5px 12px;border-radius:20px;font-size:12px" onclick="setRapido('semana')">Esta semana</button>
          <button class="btn btn-ghost" style="padding:5px 12px;border-radius:20px;font-size:12px" onclick="setRapido('mes')">Este mes</button>
          <div style="display:flex;align-items:center;gap:6px;margin-left:4px">
            <span style="font-size:12px;color:var(--text2)">Desde</span>
            <input type="date" id="d-desde" style="font-size:12px;padding:4px 8px;width:auto"/>
            <span style="font-size:12px;color:var(--text2)">Hasta</span>
            <input type="date" id="d-hasta" style="font-size:12px;padding:4px 8px;width:auto"/>
            <button class="btn btn-primary" style="padding:5px 14px;font-size:12px" onclick="renderDashboard()">Ver</button>
          </div>
        </div>
      </div>

      <div class="metrics-grid">
```

- [ ] Find lines 303–312 (the two `metrics-grid` rows of metric cards):
```html
        <div class="metric-card blue"><div class="metric-label">Entradas hoy</div><div class="metric-value" id="d-ent">—</div><div class="metric-sub">viajes</div></div>
        <div class="metric-card green"><div class="metric-label">Salidas hoy</div><div class="metric-value" id="d-sal">—</div><div class="metric-sub">volteos</div></div>
        <div class="metric-card"><div class="metric-label">Balance pendiente</div><div class="metric-value" id="d-bal">—</div><div class="metric-sub">sin recolectar hoy</div></div>
        <div class="metric-card"><div class="metric-label">Total histórico</div><div class="metric-value" id="d-tot">—</div><div class="metric-sub">registros</div></div>
      </div>
      <div class="metrics-grid">
        <div class="metric-card blue"><div class="metric-label">m³ entrada hoy</div><div class="metric-value" id="d-m3-eh">—</div><div class="metric-sub">metros cúbicos</div></div>
        <div class="metric-card green"><div class="metric-label">m³ salida hoy</div><div class="metric-value" id="d-m3-sh">—</div><div class="metric-sub">metros cúbicos</div></div>
        <div class="metric-card"><div class="metric-label">m³ entrada total</div><div class="metric-value" id="d-m3-et">—</div><div class="metric-sub">histórico</div></div>
        <div class="metric-card"><div class="metric-label">m³ salida total</div><div class="metric-value" id="d-m3-st">—</div><div class="metric-sub">histórico</div></div>
```
Replace with:
```html
        <div class="metric-card blue"><div class="metric-label">Entradas del periodo</div><div class="metric-value" id="d-ent">—</div><div class="metric-sub">viajes</div></div>
        <div class="metric-card green"><div class="metric-label">Salidas del periodo</div><div class="metric-value" id="d-sal">—</div><div class="metric-sub">volteos</div></div>
        <div class="metric-card"><div class="metric-label">Balance pendiente</div><div class="metric-value" id="d-bal">—</div><div class="metric-sub">sin recolectar</div></div>
        <div class="metric-card"><div class="metric-label">Total histórico</div><div class="metric-value" id="d-tot">—</div><div class="metric-sub">registros</div></div>
      </div>
      <div class="metrics-grid">
        <div class="metric-card blue"><div class="metric-label">m³ entrada periodo</div><div class="metric-value" id="d-m3-eh">—</div><div class="metric-sub">metros cúbicos</div></div>
        <div class="metric-card green"><div class="metric-label">m³ salida periodo</div><div class="metric-value" id="d-m3-sh">—</div><div class="metric-sub">metros cúbicos</div></div>
        <div class="metric-card"><div class="metric-label">m³ entrada total</div><div class="metric-value" id="d-m3-et">—</div><div class="metric-sub">histórico</div></div>
        <div class="metric-card"><div class="metric-label">m³ salida total</div><div class="metric-value" id="d-m3-st">—</div><div class="metric-sub">histórico</div></div>
```

- [ ] Find the `card-label` for historial chart (line 333):
```html
        <div class="card-label">Historial diario — últimos 14 días</div>
```
Replace with:
```html
        <div class="card-label">Historial diario — periodo seleccionado</div>
```

- [ ] Find the `card-label` for origen counts (line 338):
```html
        <div class="card-label">Registros por origen — histórico</div>
```
Replace with:
```html
        <div class="card-label">Orígenes (acumulado total)</div>
```

### Step 5 — Verify the page renders correctly in browser (manual check)

- [ ] Start local dev server (requires a real PostgreSQL DATABASE_URL in `.env` or export in shell):
  ```bash
  export DATABASE_URL="<your-external-db-url>"
  export AUTH_USER="PGA2627"
  export AUTH_PASS="Limpie\$a2627"
  python3 app.py
  ```
  Open http://localhost:5000 and navigate to Dashboard.
- [ ] Verify: filter bar appears at top with "Hoy / Esta semana / Este mes" buttons
- [ ] Verify: clicking "Esta semana" fills desde/hasta correctly (Mon–Sun of current week)
- [ ] Verify: clicking "Este mes" fills desde/hasta (1st–last day of current month)
- [ ] Verify: metric labels say "Entradas del periodo" and "m³ entrada periodo"
- [ ] Verify: historial chart shows bars for the selected date range (not always 14 days)
- [ ] Verify: origen section says "Orígenes (acumulado total)"
- [ ] Press Ctrl+C to stop the server

### Step 6 — Run all tests again

- [ ] Run: `python3 -m pytest tests/ -v`
- [ ] Expected: all 12 tests still pass

### Step 7 — Commit

- [ ] Run:
```bash
git add templates/index.html
git commit -m "feat: dashboard — barra de filtros de periodo, botones rápidos, gráfica dinámica"
```

---

## Task 3: Frontend — Historial bulk delete

**Files:**
- Modify: `templates/index.html`

### Step 1 — Add action bar HTML to Historial page

- [ ] In `index.html`, find line 356 (the closing tag of `table-header`, just before `table-wrap`):
```html
      </div>
      <div class="table-wrap">
```
(Context: this is right after the `table-actions` div that contains the count-pill and Exportar button)

Replace the `</div>` + `<div class="table-wrap">` sequence with:
```html
      </div>

      <!-- Barra de acción (oculta hasta seleccionar) -->
      <div id="h-action-bar" style="display:none; align-items:center; gap:12px;
           background:var(--red-bg); border:1px solid var(--red); border-radius:var(--radius);
           padding:8px 14px; margin-bottom:10px;">
        <span id="h-sel-count" style="font-size:13px; color:var(--red); font-weight:600">0 seleccionado(s)</span>
        <button class="btn btn-danger" onclick="eliminarSeleccionados()">🗑 Eliminar seleccionados</button>
      </div>

      <div class="table-wrap">
```

### Step 2 — Add checkbox column to table header

- [ ] In `index.html`, find the `<thead>` section of the historial table (lines 361–376):
```html
            <thead><tr>
              <th style="width:55px">ID</th>
              <th style="width:80px">Folio</th>
              <th style="width:55px">Tipo</th>
              <th style="width:95px">Fecha</th>
              <th style="width:65px">Hora</th>
              <th style="width:130px">PGA</th>
              <th style="width:120px">Detalle</th>
              <th style="width:110px">Origen</th>
              <th style="width:110px">Colonia</th>
              <th style="width:100px">Placa</th>
              <th style="width:65px">m³</th>
              <th>Observaciones</th>
            </tr></thead>
```
Replace with:
```html
            <thead><tr>
              <th style="width:36px;text-align:center"><input type="checkbox" title="Seleccionar todos" onchange="toggleTodos(this)"/></th>
              <th style="width:55px">ID</th>
              <th style="width:80px">Folio</th>
              <th style="width:55px">Tipo</th>
              <th style="width:95px">Fecha</th>
              <th style="width:65px">Hora</th>
              <th style="width:130px">PGA</th>
              <th style="width:120px">Detalle</th>
              <th style="width:110px">Origen</th>
              <th style="width:110px">Colonia</th>
              <th style="width:100px">Placa</th>
              <th style="width:65px">m³</th>
              <th>Observaciones</th>
            </tr></thead>
```

### Step 3 — Update `renderHistorial()` to add checkbox per row

- [ ] In `index.html`, find `renderHistorial()` — specifically the row template inside (lines 687–702):
```javascript
    document.getElementById('h-body').innerHTML = rows.map(r =>
      '<tr>' +
        '<td class="mono">' + r.id + '</td>' +
        '<td class="mono">' + r.folio + '</td>' +
        '<td><span class="badge ' + (r.tipo==='ENTRADA'?'badge-in':'badge-out') + '">' + (r.tipo==='ENTRADA'?'ENT':'SAL') + '</span></td>' +
        '<td>' + r.fecha + '</td>' +
        '<td>' + (r.hora||'—') + '</td>' +
        '<td style="font-weight:600">' + r.pga + '</td>' +
        '<td>' + (r.detalle||'—') + '</td>' +
        '<td>' + (r.origen||'—') + '</td>' +
        '<td>' + (r.colonia||'—') + '</td>' +
        '<td>' + (r.placa||'—') + '</td>' +
        '<td>' + (r.m3 ? parseFloat(r.m3).toFixed(2) : '—') + '</td>' +
        '<td style="max-width:200px;color:var(--text2)">' + (r.obs||'—') + '</td>' +
      '</tr>'
    ).join('');
```
Replace with:
```javascript
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
        '<td>' + (r.colonia||'—') + '</td>' +
        '<td>' + (r.placa||'—') + '</td>' +
        '<td>' + (r.m3 ? parseFloat(r.m3).toFixed(2) : '—') + '</td>' +
        '<td style="max-width:200px;color:var(--text2)">' + (r.obs||'—') + '</td>' +
      '</tr>'
    ).join('');
```

### Step 4 — Add historial JS functions

- [ ] In `index.html`, find the `// ── Export Excel` comment (line 708):
```javascript
// ── Export Excel ───────────────────────────────────────────────
function exportarExcel() {
```
Insert the following block **before** that comment:
```javascript
// ── Historial — selección y eliminación ────────────────────────
function actualizarBarraAccion() {
  const checks = document.querySelectorAll('#h-body input[type=checkbox]:checked');
  const bar = document.getElementById('h-action-bar');
  bar.style.display = checks.length > 0 ? 'flex' : 'none';
  document.getElementById('h-sel-count').textContent = checks.length + ' seleccionado(s)';
}

function toggleTodos(master) {
  document.querySelectorAll('#h-body input[type=checkbox]')
    .forEach(cb => cb.checked = master.checked);
  actualizarBarraAccion();
}

async function eliminarSeleccionados() {
  const checks = [...document.querySelectorAll('#h-body input[type=checkbox]:checked')];
  if (!checks.length) return;
  const n = checks.length;
  if (!confirm('¿Eliminar ' + n + ' registro(s)? Esta acción no se puede deshacer.')) return;

  let ok = 0, fail = 0;
  for (const cb of checks) {
    try {
      await api('/api/registros/' + cb.value, { method: 'DELETE' });
      ok++;
    } catch(e) {
      fail++;
    }
  }

  if (fail === 0) {
    toast(ok + ' registro(s) eliminado(s)');
  } else {
    toast(ok + ' eliminado(s), ' + fail + ' no se pudo(ieron) eliminar');
  }
  renderHistorial();
  updateNavBadges();
}

```

### Step 5 — Verify historial bulk delete in browser (manual check)

- [ ] Start the app again and open Historial.
- [ ] Verify: each row has a checkbox at the left; the header has a "seleccionar todos" checkbox.
- [ ] Select 1+ rows → verify action bar appears in red with the count.
- [ ] Deselect all → verify action bar hides.
- [ ] Click "Seleccionar todos" → verify all rows become checked.
- [ ] With ≥1 selected, click "Eliminar seleccionados" → confirm dialog appears.
- [ ] Cancel → nothing deleted.
- [ ] Confirm → rows disappear, toast shows count, table reloads.
- [ ] Verify the sidebar badge counts update after deletion.
- [ ] Press Ctrl+C to stop.

### Step 6 — Run all tests

- [ ] Run: `python3 -m pytest tests/ -v`
- [ ] Expected: all 12 tests pass

### Step 7 — Commit

- [ ] Run:
```bash
git add templates/index.html
git commit -m "feat: historial — selección múltiple y eliminación por lote"
```

---

## Task 4: Push to GitHub (auto-deploy to Render)

**Files:** none (git only)

### Step 1 — Push all commits

- [ ] Run: `git push origin main`
- [ ] Expected: push succeeds, GitHub shows 3 new commits

### Step 2 — Verify Render deploy

- [ ] Open https://dashboard.render.com → ct-app → Deploys
- [ ] Wait for the new deploy to show "Live" (≈2–3 minutes)
- [ ] Open the app URL in browser, log in, navigate to Dashboard and Historial
- [ ] Verify both new features work in production

---

## Criterios de éxito (todos deben cumplirse)

- [ ] `python3 -m pytest tests/ -v` → 12 tests PASS
- [ ] En Historial: checkboxes visibles por fila y en encabezado
- [ ] Barra roja de acción aparece solo con ≥1 seleccionado
- [ ] Eliminación confirma antes de borrar, recarga tabla, actualiza badges
- [ ] Dashboard: botones Hoy / Esta semana / Este mes rellenan fechas correctas (UTC-6)
- [ ] Campos Desde / Hasta aceptan rango personalizado
- [ ] Métricas y gráficas reflejan el periodo elegido
- [ ] Gráfico de historial muestra barras para los días del rango (no 14 fijos)
- [ ] Sección "Orígenes (acumulado total)" no cambia con el filtro de periodo
