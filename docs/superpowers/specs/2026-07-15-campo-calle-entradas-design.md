# Diseño: Campo "Calle" en Registro de entrada

**Fecha:** 2026-07-15
**Proyecto:** Centros de Transferencia — Control de Viajes
**Repositorio:** https://github.com/LuisViveros24/centros-transferencia.git

---

## 1. Contexto y Objetivo

El formulario de Entrada ya captura "Nombre" (persona que entrega el material) y "Colonia de origen". Falta un campo para registrar la **calle** de origen del viaje.

Durante el brainstorming se confirmó:
- El campo "Nombre" existente ya cubre la necesidad de identificar a la persona — no se modifica.
- El nuevo campo "Calle" aplica **solo al módulo de Entrada** (no a Salida).
- Debe reflejarse en **Historial** y en la **exportación a Excel**.
- **No** se agrega ninguna tarjeta nueva al Dashboard — el dashboard son solo métricas agregadas y esta feature no añade un desglose por calle.

Como parte de esta misma sesión de trabajo se corrigió además un bug ya detectado y arreglado en `app.py` (duplicados en "Orígenes" del dashboard, por una lista de exclusión desactualizada) — ese fix ya está aplicado y **no** forma parte del alcance de este documento.

---

## 2. Arquitectura del cambio

**Enfoque:** replicar exactamente el patrón ya usado para el campo `colonia` (que ya sigue el mismo camino: form → API → DB → autocompletado → historial → Excel). Ningún cambio de forma nueva, solo extender el campo existente al nuevo dato.

**Archivos afectados:**
- `app.py` — columna en `init_db()`, INSERT en `crear_registro()`, SELECT en `buscar_placa()`
- `migrate_data.py` — `ALTER TABLE ADD COLUMN IF NOT EXISTS` para producción (Render)
- `templates/index.html` — campo de formulario, autocompletado, columna de Historial, `limpiarE()`

**Fuera de alcance:** `export_excel()` en `app.py` también se actualiza (mencionado explícitamente por el usuario como parte de "Historial y Excel"), pero no se toca el endpoint `/api/dashboard` ni el módulo de Salida.

---

## 3. Cambios en base de datos

### 3.1 `app.py` → `init_db()` (desarrollo local)

**Estado actual (verificado):** el `CREATE TABLE` de `init_db()` (líneas 32-48 de `app.py`) **no tiene columna `nombre`** — solo `migrate_data.py` (el script de producción) la define y la agrega vía `ALTER TABLE`. Esto es una brecha preexistente, no introducida por este cambio: si alguien crea una base de datos local nueva con `init_db()`, cualquier `INSERT` de entrada fallaría porque `crear_registro()` ya inserta incondicionalmente en la columna `nombre`, que no existiría.

**Decisión de alcance:** ya que se va a editar este mismo bloque para agregar `calle`, se corrige también la brecha agregando `nombre` al mismo tiempo (mismo criterio ya aplicado en la sección 4.3 para los headers de Excel). Resultado:

```sql
CREATE TABLE IF NOT EXISTS registros (
    ...
    origen    TEXT,
    nombre    TEXT,
    calle     TEXT,
    colonia   TEXT,
    ...
)
```

### 3.2 `migrate_data.py` (producción — Render)

Agregar, junto al `ALTER TABLE` existente de `nombre`:

```python
# Agregar columna calle si la tabla ya existía sin ella
cur.execute('''
    ALTER TABLE registros ADD COLUMN IF NOT EXISTS calle TEXT
''')
```

> Este script se corre manualmente una sola vez contra la base de producción (ver cabecera del archivo). El usuario deberá ejecutarlo después del deploy, igual que se hizo para `nombre`.

---

## 4. Cambios en el backend (`app.py`)

### 4.1 `POST /api/registros` — `crear_registro()`

Agregar `calle` al INSERT, en la misma posición relativa que `colonia`:

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

Para el registro de **Salida** (`registrarSalida()` en el frontend), no se envía `calle` — el backend usa `d.get('calle', '')` por defecto, igual que ya hace con `nombre`/`colonia`, así que no requiere cambios adicionales en la rama de Salida.

### 4.2 `GET /api/registros/buscar-placa` — `buscar_placa()`

Agregar `calle` al SELECT de autocompletado:

```python
cur.execute("""
    SELECT vehiculo, detalle, origen, nombre, calle, colonia
    FROM registros
    WHERE UPPER(placa) LIKE %s AND tipo='ENTRADA'
    ORDER BY id DESC LIMIT 1
""", (q + '%',))
```

### 4.3 `GET /api/export/excel` — `export_excel()`

Agregar columna "Calle" al reporte, junto a "Colonia":

```python
headers = ['ID', 'Folio', 'Tipo', 'Fecha', 'Hora', 'PGA', 'Detalle/Carga',
           'Origen', 'Nombre', 'Calle', 'Colonia', 'Vehículo', 'Placa', 'm³', 'Observaciones', 'Registrado']
```

```python
ws.append([
    row['id'], row['folio'], row['tipo'], row['fecha'], row['hora'],
    row['pga'], row['detalle'], row['origen'], row['nombre'], row['calle'], row['colonia'],
    row['vehiculo'], row['placa'], row['m3'], row['obs'], row['creado_en']
])
```

> **Nota:** los headers actuales de `export_excel()` (línea 321-322 de `app.py`) no incluyen "Nombre" a pesar de que la columna existe en la BD desde hace varios commits — es una omisión previa, no algo introducido por este cambio. Se agrega "Nombre" junto con "Calle" en esta pasada para que el Excel quede consistente con Historial (que sí muestra Nombre). Ajustar `col_widths` para mantener la misma cantidad de entradas que `headers`.

---

## 5. Cambios en el frontend (`templates/index.html`)

### 5.1 Formulario de Entrada — nuevo campo

La fila actual (línea ~253-274) tiene 3 columnas: Tipo de vehículo, Tipo de carga, Colonia de origen. Se cambia a una fila de 4 columnas agregando "Calle":

```html
<div class="form-grid cols-4">
  <div class="field"><label>Tipo de vehículo</label>...</div>
  <div class="field"><label>Tipo de carga</label>...</div>
  <div class="field"><label>Calle</label><input type="text" id="e-calle" placeholder="Ej. Av. Reforma..."/></div>
  <div class="field"><label>Colonia de origen</label><input type="text" id="e-colonia" placeholder="Ej. Col. Centro..."/></div>
</div>
```

> Si `cols-4` no existe como clase CSS reutilizable, se define análoga a `cols-3` (grid con 4 columnas iguales) o se ajusta a 2 filas de 2 si el espacio horizontal no alcanza en móvil — a resolver durante implementación siguiendo el CSS existente.

### 5.2 `registrarEntrada()` — incluir calle en el POST

```javascript
body: JSON.stringify({
  ...
  nombre: document.getElementById('e-nombre').value.trim(),
  calle: document.getElementById('e-calle').value.trim(),
  colonia: document.getElementById('e-colonia').value.trim(),
  ...
})
```

### 5.3 `limpiarE()` — incluir `e-calle` en el reset

```javascript
['e-fecha','e-hora','e-origen','e-nombre','e-vehiculo','e-carga','e-calle','e-colonia','e-placa','e-m3','e-obs','e-otro-txt']
  .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
```

### 5.4 Autocompletado por placa

`aplicarAutocompletado()` — agregar junto a `colonia`:

```javascript
if (r.calle)    document.getElementById('e-calle').value    = r.calle;
if (r.colonia)  document.getElementById('e-colonia').value  = r.colonia;
```

El resumen del hint (`_buscarPlaca()`) no necesita cambio — sigue usando `vehiculo, detalle, origen, nombre`.

### 5.5 Historial — nueva columna

Encabezado de tabla (línea ~438-439), agregar "Calle" junto a "Colonia":

```html
<th style="width:140px">Nombre</th>
<th style="width:110px">Calle</th>
<th style="width:110px">Colonia</th>
```

Renderizado de fila (línea ~843-844):

```javascript
'<td>' + (r.nombre||'—') + '</td>' +
'<td>' + (r.calle||'—') + '</td>' +
'<td>' + (r.colonia||'—') + '</td>' +
```

Los registros de tipo **SALIDA** no tienen `calle` — la celda mostrará `—`, igual que ya ocurre con `nombre`/`colonia` en salidas.

---

## 6. Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app.py` | `init_db()` agrega columna `calle`; `crear_registro()` incluye `calle` en INSERT; `buscar_placa()` incluye `calle` en SELECT; `export_excel()` agrega columnas Nombre y Calle |
| `migrate_data.py` | `ALTER TABLE registros ADD COLUMN IF NOT EXISTS calle TEXT` |
| `templates/index.html` | Campo `e-calle` en formulario de Entrada; `registrarEntrada()` envía `calle`; `limpiarE()` resetea `e-calle`; autocompletado aplica `calle`; columna "Calle" en tabla de Historial |

---

## 7. Criterios de éxito

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
