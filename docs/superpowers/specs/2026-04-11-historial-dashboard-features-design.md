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

El endpoint `DELETE /api/registros/<id>` ya existe y funciona — no requiere cambios.

---

## 3. Funcionalidad 1 — Eliminar registros del Historial

### 3.1 Cambios en la tabla (`index.html`)

**Nueva columna de checkbox:**
- Primera columna de la tabla: `<th>` con checkbox "seleccionar todos"
- Cada fila `<tr>` tiene un `<td>` con checkbox cuyo `value` es el `id` del registro

**Barra de acción (oculta por defecto):**
```html
<div id="h-action-bar" style="display:none">
  <span id="h-sel-count">0 seleccionados</span>
  <button onclick="eliminarSeleccionados()">🗑 Eliminar seleccionados</button>
</div>
```

La barra aparece automáticamente cuando `checkboxesSeleccionados.length > 0` y desaparece cuando no hay ninguno seleccionado.

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

// Eliminar los seleccionados
async function eliminarSeleccionados() {
  const checks = [...document.querySelectorAll('#h-body input[type=checkbox]:checked')];
  if (!checks.length) return;
  const n = checks.length;
  if (!confirm(`¿Eliminar ${n} registro(s)? Esta acción no se puede deshacer.`)) return;
  
  for (const cb of checks) {
    await api('/api/registros/' + cb.value, { method: 'DELETE' });
  }
  toast(n + ' registro(s) eliminado(s)');
  renderHistorial();  // recargar tabla
  updateNavBadges();  // actualizar contadores del sidebar
}
```

### 3.2 Comportamiento esperado

1. Usuario va a Historial
2. Ve checkboxes al inicio de cada fila
3. Selecciona uno o varios (o usa "seleccionar todos")
4. Aparece la barra roja con el conteo y el botón eliminar
5. Hace clic → `confirm()` pregunta "¿Eliminar N registro(s)?"
6. Si confirma: se eliminan uno a uno, se recarga la tabla, aparece toast de confirmación
7. Si cancela: no pasa nada

---

## 4. Funcionalidad 2 — Filtro de periodo en el Dashboard

### 4.1 Cambio en `app.py`

El endpoint `/api/dashboard` pasa de aceptar `fecha` (un solo día) a aceptar `desde` y `hasta` (rango):

```python
# ANTES
hoy = request.args.get('fecha', str(date.today()))
# Todas las queries usaban: WHERE fecha=%s → [hoy]

# DESPUÉS
desde = request.args.get('desde', str(date.today()))
hasta  = request.args.get('hasta',  str(date.today()))
# Todas las queries usan: WHERE fecha BETWEEN %s AND %s → [desde, hasta]
```

**Queries afectadas (todas en `dashboard()`):**
- `COUNT(*) entradas del periodo` → `WHERE fecha BETWEEN %s AND %s AND tipo='ENTRADA'`
- `COUNT(*) salidas del periodo` → `WHERE fecha BETWEEN %s AND %s AND tipo='SALIDA'`
- `SUM(m3) entradas del periodo` → ídem
- `SUM(m3) salidas del periodo` → ídem
- Flujo por PGA (loop de 5 PGAs × 4 queries) → ídem
- Conteo por origen → no filtra por fecha (es acumulado total — no cambia)
- Historial de días → `WHERE fecha BETWEEN %s AND %s` (ya no se limita a 14 días fijos; muestra todos los días del rango)

**Nombres de campos en el JSON de respuesta:**
- `ent_hoy` → `ent_periodo`
- `sal_hoy` → `sal_periodo`
- `m3_ent_hoy` → `m3_ent_periodo`
- `m3_sal_hoy` → `m3_sal_periodo`
- `ent_tot`, `sal_tot`, `m3_ent_tot`, `m3_sal_tot` → se mantienen (son acumulados totales, sin filtro de fecha)

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
| Hoy | `today` | `today` |
| Esta semana | Lunes de la semana actual | Domingo de la semana actual |
| Este mes | 1º del mes actual | Último día del mes actual |

Al hacer clic en un botón rápido: rellena automáticamente los campos desde/hasta y llama `renderDashboard()`.

**Campos manuales:** `<input type="date">` para desde y hasta + botón "Ver" que llama `renderDashboard()`.

**Al cargar la página:** selecciona "Hoy" por defecto.

**Lógica JavaScript:**

```javascript
function setRapido(tipo) {
  const hoy = new Date();
  let desde, hasta;
  if (tipo === 'hoy') {
    desde = hasta = todayStr();
  } else if (tipo === 'semana') {
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - ((hoy.getDay()+6)%7));
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    desde = lunes.toISOString().split('T')[0];
    hasta = domingo.toISOString().split('T')[0];
  } else if (tipo === 'mes') {
    desde = hoy.getFullYear() + '-' + String(hoy.getMonth()+1).padStart(2,'0') + '-01';
    const ultimo = new Date(hoy.getFullYear(), hoy.getMonth()+1, 0);
    hasta = ultimo.toISOString().split('T')[0];
  }
  document.getElementById('d-desde').value = desde;
  document.getElementById('d-hasta').value  = hasta;
  renderDashboard();
}
```

**`renderDashboard()` actualizado:**
```javascript
async function renderDashboard() {
  const desde = document.getElementById('d-desde').value || todayStr();
  const hasta  = document.getElementById('d-hasta').value  || todayStr();
  const d = await api('/api/dashboard?desde=' + desde + '&hasta=' + hasta);
  // Actualiza métricas, gráficas, etc. usando d.ent_periodo, d.sal_periodo, etc.
}
```

**Etiquetas actualizadas en las tarjetas de métricas:**
- "Entradas hoy" → "Entradas del periodo"
- "Salidas hoy" → "Salidas del periodo"
- "m³ entrada hoy" → "m³ entrada periodo"
- "m³ salida hoy" → "m³ salida periodo"

### 4.3 Gráfico de historial

El gráfico de barras de los últimos 14 días se convierte en gráfico del rango seleccionado:
- Muestra un punto por cada día dentro del rango desde/hasta
- Si el rango es "Hoy" → solo 1 barra
- Si el rango es "Este mes" → hasta 31 barras
- Si el rango es muy largo (>60 días), el gráfico sigue mostrando todos los días (Chart.js lo maneja sin truncar)

---

## 5. Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app.py` | Reemplazar `fecha` por `desde`/`hasta` en `dashboard()`, actualizar todas las queries y los nombres de los campos del JSON |
| `templates/index.html` | (1) Columna checkbox + barra de eliminación en Historial; (2) Barra de filtros de periodo en Dashboard; (3) Actualizar `renderDashboard()` y etiquetas de métricas |

---

## 6. Criterios de éxito

- [ ] En Historial: se pueden seleccionar registros con checkboxes (individual y "todos")
- [ ] La barra de acción aparece solo cuando hay al menos un checkbox marcado
- [ ] Al confirmar la eliminación, los registros desaparecen de la tabla
- [ ] Los contadores del sidebar se actualizan tras eliminar
- [ ] En Dashboard: los botones "Hoy", "Esta semana", "Este mes" funcionan correctamente
- [ ] Los campos Desde/Hasta permiten ingresar fechas personalizadas
- [ ] Las métricas y gráficas reflejan el periodo seleccionado
- [ ] El dashboard sigue mostrando "Hoy" por defecto al abrirlo
- [ ] Los totales acumulados (toda la historia) no se ven afectados por el filtro de periodo
