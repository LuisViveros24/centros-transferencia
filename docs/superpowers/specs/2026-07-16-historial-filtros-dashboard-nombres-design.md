# Diseño: Filtros en Historial + "Personas frecuentes" en Dashboard

**Fecha:** 2026-07-16
**Proyecto:** Centros de Transferencia — Control de Viajes
**Repositorio:** https://github.com/LuisViveros24/centros-transferencia.git

---

## 1. Contexto y Objetivo

Dos mejoras solicitadas por el usuario, independientes entre sí, agrupadas en un solo spec (mismo patrón usado en `2026-04-11-historial-dashboard-features-design.md`):

1. **Historial — Filtros por columna:** con 7,100+ registros y creciendo, encontrar un registro específico en la tabla de Historial requiere hacer scroll manual. Se necesitan filtros por columna, directamente en el encabezado de la tabla.

2. **Dashboard — "Personas frecuentes":** se necesita saber quién (campo Nombre) genera más viajes de entrada, para identificar patrones de uso.

Elegido durante el brainstorming (con compañero visual): estilo de filtro **fila fija bajo encabezados** (no íconos con menú desplegable), por ser más simple de usar en celular — el dispositivo principal de los operadores.

---

## 2. Funcionalidad 1 — Filtros por columna en Historial

### 2.1 Dónde viven los filtros

Una segunda fila `<tr>` dentro de `<thead>` (`templates/index.html`, tabla `#h-tbl`), inmediatamente debajo de la fila de encabezados actual (línea ~424-441), siempre visible — no es un panel que se abre/cierra.

**Consecuencia directa para 2.6:** "siempre visible" significa que la tabla completa (con su `<thead>` y la fila de filtros) debe permanecer en pantalla incluso cuando el filtro activo no encuentra ninguna coincidencia — de lo contrario el usuario no podría ver ni ajustar los filtros que él mismo puso, justo cuando más los necesita. Ver 2.6 para el cambio que esto implica en el manejo del estado vacío.

### 2.2 Controles por columna

| Columna | Control | Comportamiento |
|---|---|---|
| (checkbox) | — | sin filtro (celda vacía, solo espaciador) |
| ID | — | sin filtro |
| Folio | texto | contiene (sin distinguir mayúsculas/minúsculas) |
| Tipo | `<select>` | `Todos` / `ENTRADA` / `SALIDA` — igualdad exacta |
| Fecha | `<input type="date">` | coincide con esa fecha exacta |
| Hora | — | sin filtro |
| PGA | `<select>` | `Todos` + los 5 PGA conocidos (`ROVIROSA WADE`, `LEY SAULO`, `ESTERITO`, `RECOVERDE`, `COMPRESORA`) — igualdad exacta |
| Detalle | — | sin filtro |
| Origen | `<select>` | `Todos` + los 6 orígenes conocidos (`NEGOCIO`, `RECOLECTORES`, `CASA-HABITACIÓN`, `CEA`, `LA OLA`, `CONTRATISTAS`) — igualdad exacta |
| Nombre | texto | contiene |
| Calle | texto | contiene |
| Colonia | texto | contiene |
| Placa | texto | contiene |
| m³ | — | sin filtro |
| Observaciones | texto | contiene |

Todos los filtros activos se combinan con **Y** (deben cumplirse todos a la vez). Un filtro vacío/en "Todos" no restringe nada.

> El `<select>` de PGA debe generarse a partir de la constante `PGAS` ya existente (`templates/index.html:454`), no repetir la lista de valores en un segundo lugar del código.

### 2.3 Arquitectura: filtrado 100% en el navegador

`renderHistorial()` (`templates/index.html:828`) ya hace `await api('/api/registros')` **sin parámetros** — trae siempre la tabla completa de una sola vez. No se toca el backend ni el endpoint `GET /api/registros`.

Cambio de arquitectura interna:
- El arreglo completo de registros se guarda en una variable de módulo (`let _historialRows = []`), en vez de usarse una sola vez y descartarse.
- Se añade `let _historialFiltros = {...}` con el valor actual de cada filtro.
- Una nueva función `aplicarFiltrosHistorial()` recorre `_historialRows`, aplica `matchesFiltroHistorial(r)` a cada uno, y vuelve a construir el `<tbody>` **solo con las filas que pasan el filtro** (no se ocultan con CSS — simplemente no se agregan al DOM).
- `renderHistorial()` pasa a: pedir los datos una vez, guardarlos en `_historialRows`, y llamar a `aplicarFiltrosHistorial()` para el render inicial (con filtros vacíos, el resultado es idéntico al comportamiento actual).
- Los `<input>`/`<select>` de la fila de filtros llaman a `aplicarFiltrosHistorial()`: los `<select>`/`<input type="date">` al evento `change` (inmediato), los `<input type="text">` al evento `input` con un debounce de ~250ms (mismo patrón que ya usa el autocompletado de placa, `_placaTimer`, línea ~905).

**Por qué al DOM y no con `display:none`:** porque de esa forma, "seleccionar todos" (`toggleTodos`) y "eliminar seleccionados" (`eliminarSeleccionados`) — que ya operan sobre `document.querySelectorAll('#h-body input[type=checkbox]')` — automáticamente **solo ven las filas visibles**, sin tocar esas dos funciones. Esto resuelve directamente la decisión de diseño confirmada: nunca se debe poder seleccionar/eliminar algo oculto por un filtro.

Al cambiar cualquier filtro, se limpia la selección visual (el checkbox "seleccionar todos" del encabezado se desmarca) para no dejar un estado de selección ambiguo entre el conjunto visible anterior y el nuevo.

### 2.4 El caso especial de `Fecha`

`r.fecha` no llega como `"2026-07-16"` — Flask serializa objetos `date` de Python en formato HTTP (`"Thu, 16 Jul 2026 00:00:00 GMT"`), y así es como se ve hoy en la columna Fecha del Historial en producción (captura de pantalla del usuario). Comparar ese string directamente contra el valor de un `<input type="date">` (que da `"2026-07-16"`) nunca coincidiría.

Se agrega un helper:
```javascript
function fechaToYMD(rawFecha) {
  const d = new Date(rawFecha);
  return d.getUTCFullYear() + '-' + String(d.getUTCMonth()+1).padStart(2,'0') + '-' + String(d.getUTCDate()).padStart(2,'0');
}
```
Usa los getters **UTC** (no locales) a propósito: como `fecha` es una columna `DATE` sin hora, el `"00:00:00 GMT"` es solo un artefacto de serialización, no un instante real que deba convertirse a hora de México — convertirlo con getters locales correría la fecha un día hacia atrás (mismo tipo de bug ya corregido antes en el Dashboard con `dateToLocalStr`, ver `2026-04-11-historial-dashboard-features-design.md`).

**Incluido en esta misma tarea, por estar directamente relacionado:** ya que se necesita `fechaToYMD()` para el filtro, se usa también para mostrar la columna Fecha del Historial como `DD/MM/YYYY` en vez del string HTTP crudo — es una mejora pequeña y de bajo riesgo a un problema real de legibilidad (la celda se ve truncada y con formato técnico en la captura del usuario), directamente en el código que ya se está tocando.

### 2.5 "Limpiar filtros"

Botón nuevo junto a "Exportar Excel" en `.table-actions` (línea ~407-410): `limpiarFiltrosHistorial()` vacía los **10** campos con filtro (Folio, Tipo, Fecha, PGA, Origen, Nombre, Calle, Colonia, Placa, Observaciones — la lista completa de la tabla en 2.2), reinicia `_historialFiltros`, y vuelve a llamar `aplicarFiltrosHistorial()`.

### 2.6 Contador y estado vacío con filtros activos

`#h-count` (el pill "N registros") pasa a reflejar siempre el **conjunto filtrado/visible**, no el total cargado — se actualiza dentro de `aplicarFiltrosHistorial()` en cada re-render, usando `filtered.length` en vez de `rows.length`.

**Cambio respecto al comportamiento actual:** hoy, cuando `rows.length === 0`, `renderHistorial()` oculta la tabla completa (`tbl.style.display='none'`) y muestra un `<div id="h-empty">` aparte. Eso ya no sirve porque ocultaría también la fila de filtros (contradice 2.1 — "siempre visible"). El nuevo comportamiento:

- La tabla (`<thead>`, incluida la fila de filtros) **siempre se muestra** — se elimina el toggle `tbl.style.display='none'`.
- Cuando `filtered.length === 0`, en vez de vaciar `#h-body`, se le pone una sola fila con un mensaje, usando `colspan` para ocupar todas las columnas: `<tr><td colspan="15" style="text-align:center;color:var(--text2);padding:20px">...</td></tr>`.
- El mensaje dentro de esa fila distingue dos casos:
  - **Sin ningún filtro activo y `_historialRows.length === 0`** (base de datos genuinamente vacía): "No hay registros aún."
  - **Con algún filtro activo (o incluso sin filtros, pero `_historialRows.length > 0` y aun así 0 coincidencias — no debería pasar sin filtros, pero cubre el caso por seguridad) y 0 coincidencias**: "Ningún registro coincide con los filtros."
- El `<div id="h-empty">` separado ya no se usa y se elimina del HTML — su función la cumple ahora la fila dentro de `#h-body`.

`aplicarFiltrosHistorial()` decide cuál mensaje mostrar comparando `_historialRows.length` (total real) contra si hay algún filtro con valor en `_historialFiltros`.

### 2.7 Fuera de alcance

- `GET /api/registros` no cambia — sigue devolviendo todo, sin parámetros de filtro por columna.
- `GET /api/export/excel` no cambia — la exportación sigue siendo de **todos** los registros, sin importar los filtros activos en pantalla. No se pidió que la exportación respete el filtro.
- No se agrega paginación. Con el volumen actual (~7,100 registros) el filtrado en el navegador es instantáneo; si el volumen crece mucho más, sería un cambio aparte.

---

## 3. Funcionalidad 2 — "Personas frecuentes" en Dashboard

### 3.1 Qué muestra

Nueva tarjeta en el Dashboard (`templates/index.html`, junto a la tarjeta "Orígenes (acumulado total)", línea ~392-395): personas del campo **Nombre** con **más de 3 entradas** en el periodo seleccionado (respeta `desde`/`hasta` — el mismo filtro de periodo que ya usan Entradas/Salidas/m³, a diferencia de "Orígenes" que es acumulado histórico fijo).

### 3.2 Reglas de conteo

- Solo `tipo='ENTRADA'` (Salidas no tienen Nombre).
- Nombres vacíos o solo espacios se excluyen.
- Para agrupar, se ignoran mayúsculas/minúsculas y espacios al inicio/fin (`LOWER(TRIM(nombre))`), así "Antonio Gómez" y "antonio gomez" cuentan como la misma persona.
- El nombre que se **muestra** para cada grupo es la variante más reciente que se haya escrito (por `id` descendente) — no un promedio ni la primera vez, sino la última forma en que se capturó.
- Umbral: estrictamente más de 3 (`COUNT(*) > 3`, es decir 4 o más).
- Orden: de mayor a menor cantidad.

### 3.3 Backend — `/api/dashboard`

Nueva consulta dentro de `dashboard()` (`app.py:202`), usando el helper `qa()` ya existente en la función:

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

Se agrega al JSON de respuesta:
```python
'nombres_frecuentes': [{'nombre': r['nombre'], 'count': r['c']} for r in nombres_frecuentes]
```

Ningún campo existente del JSON de `/api/dashboard` cambia de nombre o de forma — esto es puramente aditivo.

### 3.4 Frontend

Tarjeta nueva:
```html
<div class="card">
  <div class="card-label">Personas frecuentes (más de 3 entradas en el periodo)</div>
  <div id="nombres-frecuentes" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-top:4px"></div>
</div>
```

En `renderDashboard()` (`templates/index.html:699`), justo después del bloque que llena `#origen-counts` (línea ~809-820), se agrega el bloque análogo para `d.nombres_frecuentes`, con el mismo estilo de tarjeta pequeña (nombre + número grande + etiqueta), y un mensaje "Nadie superó 3 entradas en este periodo." cuando la lista viene vacía.

### 3.5 Fuera de alcance

- No se toca la tarjeta "Orígenes (acumulado total)" ni ninguna otra métrica existente del Dashboard.
- No se agrega esta métrica a la exportación de Excel — es una vista informativa del Dashboard, no un reporte descargable.
- No se resuelven inconsistencias de captura más allá de mayúsculas/espacios (ej. errores de ortografía como "Antonio Gomes" vs "Antonio Gómez" seguirán contando por separado) — normalizar ortografía requeriría un catálogo de personas, que no se pidió y sería un cambio mucho más grande.

---

## 4. Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app.py` | `dashboard()`: nueva consulta `nombres_frecuentes` y nuevo campo en el JSON de respuesta. Sin cambios en ningún otro endpoint. |
| `templates/index.html` | Historial: fila de filtros en `<thead>`, `_historialRows`/`_historialFiltros`, `aplicarFiltrosHistorial()`, `matchesFiltroHistorial()`, `fechaToYMD()`, formato de la celda Fecha, botón "Limpiar filtros", ajuste a `renderHistorial()`. Dashboard: tarjeta nueva `#nombres-frecuentes` + bloque de render en `renderDashboard()`. |

---

## 5. Criterios de éxito

**Historial:**
- [ ] La tabla de Historial muestra una fila de filtros fija debajo de los encabezados
- [ ] Filtrar por Tipo, PGA u Origen usa un menú desplegable con los valores conocidos
- [ ] Filtrar por Fecha usa un selector de fecha y coincide con el día exacto (sin importar el desfase de zona horaria)
- [ ] Filtrar por Folio, Nombre, Calle, Colonia, Placa u Observaciones busca coincidencias parciales, sin distinguir mayúsculas/minúsculas
- [ ] Combinar dos o más filtros aplica todos a la vez (Y lógico)
- [ ] "Seleccionar todos" y "Eliminar seleccionados" solo afectan las filas visibles según el filtro activo
- [ ] Cambiar un filtro limpia cualquier selección previa
- [ ] El botón "Limpiar filtros" vacía los 10 campos con filtro de un clic
- [ ] El pill de conteo ("N registros") refleja el conjunto filtrado, no el total cargado
- [ ] Si un filtro no encuentra nada, el mensaje dice "Ningún registro coincide con los filtros." (no "No hay registros aún.")
- [ ] La fila de filtros sigue visible incluso cuando el filtro activo no encuentra ninguna coincidencia (nunca se oculta la tabla completa)
- [ ] La columna Fecha se muestra en formato `DD/MM/YYYY` en vez del string HTTP crudo
- [ ] La exportación a Excel sigue exportando todos los registros, sin importar los filtros activos en pantalla

**Dashboard:**
- [ ] Aparece una tarjeta "Personas frecuentes" junto a "Orígenes (acumulado total)"
- [ ] Solo cuenta registros de tipo ENTRADA
- [ ] Solo muestra personas con más de 3 entradas en el periodo seleccionado (Hoy/Esta semana/Este mes/rango manual)
- [ ] Cambiar el periodo del Dashboard actualiza esta tarjeta (a diferencia de "Orígenes", que no cambia)
- [ ] "Antonio Gómez" y "antonio gomez " cuentan como la misma persona
- [ ] Nombres vacíos nunca aparecen en la lista
- [ ] Si nadie supera el umbral, se muestra un mensaje en vez de una tarjeta vacía sin explicación
