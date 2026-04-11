# Diseño: Eliminar registros del Historial + Filtro de periodo en Dashboard

**Fecha:** 2026-04-11  
**Proyecto:** Centros de Transferencia — Control de Viajes  
**Repositorio:** https://github.com/LuisViveros24/centros-transferencia.git

---

## 1. Contexto y Objetivo

La app ya está desplegada en Render.com con PostgreSQL. Se necesitan dos mejoras:

1. **Historial — Eliminar registros:** Los operadores hicieron registros de prueba y no pueden borrarlos. Se necesita poder seleccionar uno o varios registros y eliminarlos desde la vista de Historial.

2. **Dashboard — Filtro de periodo:** El dashboard actualmente muestra solo el día de hoy. Se necesita poder ver las estadísticas para cualquier rango de fechas (ej. semana, mes, o fechas personalizadas).

---

## 2. Arquitectura del cambio

**Enfoque:** Opción A — mínimos cambios, máxima estabilidad.

- `index.html` — recibe la mayoría de los cambios (UI de checkboxes + barra de filtros)
- `app.py` — un solo cambio: el endpoint `/api/dashboard` acepta `desde`/`hasta` en lugar de solo `fecha`

El endpoint `DELETE /api/registros/<id>` ya existe y funciona — no requiere cambios en el backend.

---

## 3. Funcionalidad 1 — Eliminar registros del Historial

### 3.1 Cambios en la tabla (`index.html`)

**Nueva columna de checkbox:**
- Primera columna de la tabla: `<th>` con un checkbox "seleccionar todos" cuyo `onchange` llama a `toggleTodos(this)`
- Cada fila `<tr>` tiene un `<td>` con checkbox cuyo `value` es el `id` del registro y `onchange` llama a `actualizarBarraAccion()`

**Barra de acción (oculta por defecto):**

```html
<div id="h-action-bar" style="display:none; align-items:center; gap:12px;
     background:#fff3f2; border:1px solid #e57373; border-radius:8px;
     padding:8px 14px; margin-bottom:10px;">
  <span id="h-sel-count" style="font-size:13px; color:#c43a2a; font-weight:600">
    0 seleccionado(s)
  </span>
  <button class="btn btn-danger" onclick="eliminarSeleccionados()">
    🗑 Eliminar seleccionados
  </button>
</div>
```

La barra aparece automáticamente cuando hay al menos 1 checkbox marcado y desaparece cuando no hay ninguno.

**Lógica JavaScript:**

```javascript
// Actualizar barra según selección
function actualizarBarraAccion() {
  const checks = document.querySelectorAll('#h-body input[type=checkbox]:checked');
  const bar = document.getElementById('h-action-bar');
  bar.style.display = checks.length > 0 ? 'flex' : 'none';
  document.getElementById('h-sel-count').textContent = checks.length + ' seleccionado(s)';
}

// Seleccionar / deseleccionar todos
function toggleTodos(master) {
  document.querySelectorAll('#h-body input[type=checkbox]')
    .forEach(cb => cb.checked = master.checked);
  actualizarBarraAccion();
}

// Eliminar los seleccionados con manejo de errores parciales
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
  renderHistorial();    // recargar tabla
  updateNavBadges();    // actualizar contadores del sidebar
}
```

### 3.2 Comportamiento esperado

1. Usuario va a Historial
2. Ve checkboxes al inicio de cada fila y en el encabezado
3. Selecciona uno o varios (o usa "seleccionar todos" en el encabezado)
4. Aparece la barra roja con el conteo y el botón eliminar
5. Hace clic → `confirm()` pregunta "¿Eliminar N registro(s)?"
6. Si confirma: se eliminan uno a uno; si todos se eliminan correctamente aparece toast de éxito; si alguno falla aparece toast indicando cuántos se eliminaron y cuántos fallaron
7. La tabla se recarga y los contadores del sidebar se actualizan
8. Si cancela: no pasa nada

---

## 4. Funcionalidad 2 — Filtro de periodo en el Dashboard

### 4.1 Cambio en `app.py`

El endpoint `/api/dashboard` pasa de aceptar `fecha` (un solo día) a aceptar `desde` y `hasta` (rango inclusivo):

```python
# ANTES
hoy = request.args.get('fecha', str(date.today()))
# Queries usaban: WHERE fecha=%s → [hoy]

# DESPUÉS
desde = request.args.get('desde', str(date.today()))
hasta  = request.args.get('hasta',  str(date.today()))
# Queries usan: WHERE fecha BETWEEN %s AND %s → [desde, hasta]
```

**Queries afectadas (todas en `dashboard()`):**
- `COUNT(*) entradas del periodo` → `WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA'`
- `COUNT(*) salidas del periodo` → `WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'`
- `SUM(m3) entradas del periodo` → ídem
- `SUM(m3) salidas del periodo` → ídem
- Flujo por PGA (loop de 5 PGAs × 4 queries) → ídem — cada query agrega `AND fecha BETWEEN %s AND %s`
- **Conteo por origen → no filtra por fecha** (es acumulado total histórico — no cambia)
- Historial de días → `WHERE fecha BETWEEN %s AND %s` — ya no se limita a 14 días fijos

**Variables Python renombradas (para claridad interna):**

| Variable antes | Variable después |
|---|---|
| `ent_hoy` | `ent_periodo` |
| `sal_hoy` | `sal_periodo` |
| `m3_eh` | `m3_ep` |
| `m3_sh` | `m3_sp` |
| `m3_et` | `m3_et` (sin cambio) |
| `m3_st` | `m3_st` (sin cambio) |

**Campo `balance`:** se recalcula con los nombres nuevos:
```python
'balance': max(0, ent_periodo - sal_periodo)
```

**Campos del JSON de respuesta:**

| Campo antes | Campo después | Descripción |
|---|---|---|
| `ent_hoy` | `ent_periodo` | Entradas en el rango seleccionado |
| `sal_hoy` | `sal_periodo` | Salidas en el rango seleccionado |
| `balance` | `balance` | Sin cambio (usa nuevas variables Python) |
| `total` | `total` | Sin cambio — total histórico de todos los registros |
| `m3_ent_hoy` | `m3_ent_periodo` | m³ entradas en el rango |
| `m3_sal_hoy` | `m3_sal_periodo` | m³ salidas en el rango |
| `m3_ent_tot` | `m3_ent_tot` | Sin cambio — acumulado total histórico |
| `m3_sal_tot` | `m3_sal_tot` | Sin cambio — acumulado total histórico |
| `pga_flow` | `pga_flow` | Sin cambio en nombre; los valores reflejan el rango |
| `origen_counts` | `origen_counts` | Sin cambio — siempre es acumulado total (ver nota) |
| `historial` | `historial` | Sin cambio en nombre; devuelve todos los días del rango |

> **Nota sobre `origen_counts`:** Este bloque no filtra por fecha — es intencional y refleja el acumulado histórico total de todos los orígenes. En el HTML, la sección de orígenes debe mostrar la etiqueta **"Orígenes (acumulado total)"** para que el usuario entienda que no cambia con el filtro de periodo.

> **Nota sobre `ent_tot`/`sal_tot`:** El campo actual `total` representa el conteo total de todos los registros (entradas + salidas). No existen campos separados `ent_tot`/`sal_tot` — no se crean nuevos en esta feature.

### 4.2 Cambio en `index.html` — Barra de filtros del Dashboard

Se agrega una barra de filtros en la parte superior de la página del Dashboard, antes de las métricas:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Periodo: [Hoy] [Esta semana] [Este mes]  Desde [____] Hasta [____] [Ver] │
└──────────────────────────────────────────────────────────────────────┘
```

**Botones rápidos:**

| Botón | Desde | Hasta |
|---|---|---|
| Hoy | hoy (hora local) | hoy (hora local) |
| Esta semana | Lunes de la semana actual (hora local) | Domingo de la semana actual (hora local) |
| Este mes | 1º del mes actual (hora local) | Último día del mes actual (hora local) |

Al hacer clic en un botón rápido: rellena automáticamente los campos `d-desde`/`d-hasta` y llama `renderDashboard()`.

**Campos manuales:** `<input type="date" id="d-desde">` y `<input type="date" id="d-hasta">` + botón "Ver" que llama `renderDashboard()`.

**Al cargar la página:** llama `setRapido('hoy')` para inicializar con el día actual.

**Lógica JavaScript — usar aritmética de fecha local (NO `toISOString()` para evitar error de zona horaria UTC-6):**

```javascript
// Convierte un objeto Date a string YYYY-MM-DD usando hora LOCAL (no UTC)
function dateToLocalStr(d) {
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}

// ACTUALIZAR todayStr() para usar hora local en lugar de UTC
// (la versión actual usa toISOString() que puede devolver mañana en UTC-6 a medianoche)
// Esta actualización corrige también autoNow() y updateNavBadges() que llaman todayStr()
function todayStr() { return dateToLocalStr(new Date()); }

function setRapido(tipo) {
  const hoy = new Date();
  let desde, hasta;

  if (tipo === 'hoy') {
    desde = hasta = todayStr();  // todayStr() ya usa hora local en la app actual

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

**`renderDashboard()` actualizado — usa `ent_periodo`, `sal_periodo`, etc.:**

```javascript
async function renderDashboard() {
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
  // ... resto igual (pga_flow, origen_counts, historial)
}
```

**Etiquetas actualizadas en las tarjetas de métricas:**
- "Entradas hoy" → "Entradas del periodo"
- "Salidas hoy" → "Salidas del periodo"
- "m³ entrada hoy" → "m³ entrada periodo"
- "m³ salida hoy" → "m³ salida periodo"

### 4.3 Gráfico de historial — reescritura del bloque JS

El bloque actual (lines ~637-658 de `index.html`) genera un array de 14 días fijo en el cliente. Debe reemplazarse para conducir el eje X desde el rango seleccionado (`desde`/`hasta`) usando la respuesta del servidor:

```javascript
// NUEVO bloque de historial — reemplaza el bloque con allDays/histMap
const histMap = {};
d.historial.forEach(h => {
  // h.fecha viene como objeto Date de psycopg2; el JSON lo serializa como string YYYY-MM-DD
  const key = typeof h.fecha === 'string' ? h.fecha.slice(0, 10) : h.fecha;
  histMap[key] = h;
});

// Generar todos los días del rango desde–hasta en hora local
// Usar new Date(año, mes-1, día) para garantizar hora local (evita bug UTC)
function parseDateLocal(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}
const allDays = [];
const cur = parseDateLocal(desde);
const end = parseDateLocal(hasta);
while (cur <= end) {
  allDays.push(dateToLocalStr(cur));
  cur.setDate(cur.getDate() + 1);
}

const dayLabels  = allDays.map(dd => { const p = dd.split('-'); return p[2] + '/' + p[1]; });
const entByDay   = allDays.map(dd => histMap[dd] ? Number(histMap[dd].entradas) : 0);
const salByDay   = allDays.map(dd => histMap[dd] ? Number(histMap[dd].salidas)  : 0);

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
```

> **Nota:** `autoSkip: true` y `maxTicksLimit: 31` evitan que Chart.js dibuje un eje ilegible cuando el rango es muy largo (ej. un año).

---

## 5. Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app.py` | En `dashboard()`: reemplazar `fecha`→`desde`/`hasta`, actualizar todas las queries a `BETWEEN`, renombrar variables Python, actualizar JSON response, corregir `balance` |
| `templates/index.html` | (1) Columna checkbox + barra eliminación en Historial; (2) Barra de filtros en Dashboard; (3) `setRapido()` con `dateToLocalStr()`; (4) `renderDashboard()` con nuevos field names; (5) Reescribir bloque JS del gráfico de historial; (6) Etiqueta "Orígenes (acumulado total)" |

---

## 6. Criterios de éxito

- [ ] En Historial: se pueden seleccionar registros con checkboxes (individual y "todos")
- [ ] La barra de acción aparece solo cuando hay al menos un checkbox marcado
- [ ] Al confirmar la eliminación, los registros desaparecen de la tabla
- [ ] Si alguna eliminación falla, el toast informa cuántos se eliminaron y cuántos fallaron
- [ ] Los contadores del sidebar se actualizan tras eliminar
- [ ] En Dashboard: los botones "Hoy", "Esta semana", "Este mes" funcionan con fechas correctas en zona horaria local (México, UTC-6)
- [ ] Los campos Desde/Hasta permiten ingresar fechas personalizadas
- [ ] Las métricas y gráficas reflejan el periodo seleccionado
- [ ] El dashboard muestra "Hoy" por defecto al abrirlo
- [ ] El gráfico de historial muestra exactamente los días del rango seleccionado
- [ ] La sección de orígenes muestra la etiqueta "Orígenes (acumulado total)"
- [ ] Los totales acumulados (m³ tot, total registros) no cambian con el filtro de periodo
