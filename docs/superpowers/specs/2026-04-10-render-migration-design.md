# Diseño: Migración de ct_app_mac a Render.com con PostgreSQL

**Fecha:** 2026-04-10  
**Proyecto:** Centros de Transferencia — Control de Viajes  
**Repositorio:** https://github.com/LuisViveros24/centros-transferencia.git

---

## 1. Contexto y Objetivo

La aplicación Flask `ct_app_mac` actualmente corre en una máquina local con SQLite, accesible solo en red local. El objetivo es migrarla a Render.com con PostgreSQL para que cualquier persona con el link pueda acceder desde cualquier navegador, con protección de contraseña.

### Estado actual
- Flask + SQLite (2 tablas: `registros` y `config`)
- 6 rutas: `GET /`, `GET /api/registros`, `POST /api/registros`, `DELETE /api/registros/<id>`, `GET /api/dashboard`, `GET /api/export/excel`
- Sin autenticación
- 0 registros existentes (DB vacía, solo contador de folio en 1)

### Estado objetivo
- Flask + PostgreSQL en Render.com
- Misma lógica y rutas sin cambios
- HTTP Basic Auth en **todas** las rutas (un solo usuario)
- Accesible públicamente vía URL de Render

---

## 2. Arquitectura

```
GitHub (LuisViveros24/centros-transferencia)
        │  push → deploy automático
        ▼
Render Web Service (plan free)
  └── Python / Gunicorn / app.py
        │
        ▼
  Render PostgreSQL (plan free, misma región)
  └── DB: centros_transferencia
        tablas: registros, config
```

### Variables de entorno en Render

| Variable       | Origen                                 |
|----------------|----------------------------------------|
| `DATABASE_URL` | Auto-inyectada por Render desde la BD  |
| `AUTH_USER`    | Manual en dashboard de Render          |
| `AUTH_PASS`    | Manual en dashboard de Render          |

**Importante:** Ninguna de estas variables debe tener valor por defecto en el código. Si alguna falta, la app debe fallar al arrancar con un mensaje claro.

---

## 3. Archivos a crear o modificar

| Archivo            | Acción    | Descripción                                          |
|--------------------|-----------|------------------------------------------------------|
| `app.py`           | Modificar | SQLite → PostgreSQL + Basic Auth decorator           |
| `requirements.txt` | Crear     | flask, psycopg2-binary, gunicorn, openpyxl           |
| `render.yaml`      | Crear     | Config de deploy: web service + PostgreSQL gratuito  |
| `migrate_data.py`  | Crear     | Crea tablas en PostgreSQL (ejecutar una sola vez)    |
| `README_DEPLOY.md` | Crear     | Guía paso a paso para supervisores                   |

---

## 4. Cambios en `app.py`

### 4.1 Dependencias

```python
# Eliminar:
import sqlite3

# Agregar:
import psycopg2
import psycopg2.extras
from functools import wraps
from flask import Response
```

### 4.2 Configuración de conexión — sin valores por defecto en el código

```python
DATABASE_URL = os.environ.get('DATABASE_URL')
AUTH_USER    = os.environ.get('AUTH_USER')
AUTH_PASS    = os.environ.get('AUTH_PASS')

if not DATABASE_URL:
    raise RuntimeError('Falta la variable de entorno DATABASE_URL')
if not AUTH_USER or not AUTH_PASS:
    raise RuntimeError('Faltan las variables de entorno AUTH_USER o AUTH_PASS')
```

Las credenciales reales (`PGA2627` / `Limpie$a2627`) se configuran **únicamente** en el dashboard de Render como variables de entorno, nunca en el código ni en el repositorio de GitHub.

### 4.3 Función `get_db()`

```python
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
```

Las queries se ejecutan con `cursor_factory=psycopg2.extras.RealDictCursor` para mantener acceso por nombre de columna (`row['campo']`), idéntico al comportamiento de `sqlite3.Row`.

### 4.4 Función `init_db()` — solo para desarrollo local

La función `init_db()` crea las tablas. Cambios de sintaxis SQL respecto a SQLite:

- `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- `fecha TEXT NOT NULL` → `fecha DATE NOT NULL` (permite aritmética de fechas directa en PostgreSQL)
- `TEXT DEFAULT (datetime('now','localtime'))` → `TIMESTAMP DEFAULT NOW()`
- `INSERT OR IGNORE INTO config VALUES (...)` → `INSERT INTO config VALUES (...) ON CONFLICT DO NOTHING`

> **Nota importante:** Bajo Gunicorn en Render, el bloque `if __name__ == '__main__':` **nunca se ejecuta**, por lo que `init_db()` no corre en producción. La creación del esquema en producción es responsabilidad exclusiva de `migrate_data.py`, que se ejecuta manualmente una sola vez antes del primer uso.

### 4.5 Placeholders SQL

Reemplazar todos los `?` por `%s` en cada query (único cambio repetido en el código).

### 4.6 Historial 14 días — aritmética de fechas

Con `fecha` declarada como tipo `DATE` en PostgreSQL:

```sql
-- SQLite (antes):
WHERE fecha >= date(?, 'start of day', '-13 days')

-- PostgreSQL (después):
WHERE fecha >= (%s::date - INTERVAL '13 days')
```

### 4.7 Folio con bloqueo de fila — dentro de la misma transacción

Para evitar folios duplicados con acceso concurrente, `next_folio()` usa `SELECT ... FOR UPDATE`. Esta operación **debe** ejecutarse dentro del mismo bloque `with conn:` que hace el `INSERT`, de modo que el lock se mantenga activo hasta que la transacción se confirme:

```python
# CORRECTO — next_folio y el INSERT comparten la misma transacción
conn = get_db()
try:
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Bloquea la fila del contador
            cur.execute("SELECT valor FROM config WHERE clave='folio_base' FOR UPDATE")
            n = int(cur.fetchone()['valor'])
            folio = prefix + str(n).zfill(4)
            cur.execute("UPDATE config SET valor=%s WHERE clave='folio_base'", (n+1,))
            # 2. INSERT en la misma transacción (el lock se libera al commit)
            cur.execute("INSERT INTO registros (...) VALUES (...)", (...))
finally:
    conn.close()
```

### 4.8 HTTP Basic Auth — cubre las 6 rutas

El decorador `@requiere_auth` se aplica a **todas** las rutas sin excepción:

| Ruta | Método | Decorada |
|------|--------|----------|
| `/` | GET | ✓ |
| `/api/registros` | GET | ✓ |
| `/api/registros` | POST | ✓ |
| `/api/registros/<int:rid>` | DELETE | ✓ |
| `/api/dashboard` | GET | ✓ |
| `/api/export/excel` | GET | ✓ |

```python
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
```

### 4.9 Gestión de conexiones

psycopg2 no usa context manager de la misma forma que sqlite3. El patrón en cada ruta es:

```python
conn = get_db()
try:
    with conn:           # maneja commit en éxito, rollback en excepción
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
finally:
    conn.close()         # siempre cierra la conexión para liberar el slot
```

> **Límite de conexiones:** El plan gratuito de PostgreSQL en Render permite ~25 conexiones simultáneas. Dado que `get_db()` abre una conexión nueva por request y siempre la cierra en el bloque `finally`, esto es suficiente para uso normal de la app (pocos usuarios concurrentes). Si en el futuro se detectan errores de "too many connections", se puede agregar `psycopg2.pool.SimpleConnectionPool` sin cambiar la lógica de negocio.

### 4.10 Punto de entrada

```python
if __name__ == '__main__':
    init_db()   # solo se ejecuta al correr python app.py localmente
    app.run()
```

---

## 5. `requirements.txt`

```
flask
psycopg2-binary
gunicorn
openpyxl
```

---

## 6. `render.yaml`

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

> El web service y la base de datos deben estar en la **misma región** (`oregon`) para que la URL de conexión interna funcione correctamente.

---

## 7. `migrate_data.py`

Script de ejecución única desde la terminal local. Dado que la base de datos SQLite está vacía (0 registros), su función es crear el esquema inicial en PostgreSQL.

### DDL completo de PostgreSQL (diferencias respecto a SQLite en negrita)

```sql
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
);

CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

INSERT INTO config VALUES ('folio_base', '1') ON CONFLICT DO NOTHING;
```

### Pasos del script

1. Leer `DATABASE_URL` del entorno (debe ser la **URL externa** de Render, no la interna) y fallar con error claro si no está definida
2. Conectar a PostgreSQL con psycopg2
3. Ejecutar el DDL anterior dentro de una transacción
4. Confirmar e imprimir mensaje de éxito

No migra registros porque no hay ninguno en la DB de origen.

---

## 8. `README_DEPLOY.md` — Pasos de despliegue

1. Crear cuenta en [render.com](https://render.com) y conectar cuenta de GitHub
2. **New → Blueprint** → seleccionar repositorio `centros-transferencia`  
   Render detecta `render.yaml` y crea automáticamente la BD PostgreSQL y el web service en la región `oregon`  
   > ⚠️ Render lanzará un primer deploy automáticamente. **Ese deploy fallará** con un error de base de datos porque las tablas aún no existen — esto es **esperado y normal**. No es necesario hacer nada; completa los pasos 3–5 primero.
3. En el dashboard del servicio → **Environment** → agregar manualmente:
   - `AUTH_USER` = `PGA2627`
   - `AUTH_PASS` = `Limpie$a2627`
4. Obtener la **URL de conexión externa** de la base de datos:
   - Dashboard de Render → seleccionar el servicio `ct-db` → pestaña **"Connections"**
   - Copiar el campo **"External Database URL"** (empieza con `postgresql://...`)
   - ⚠️ No confundir con la "Internal Database URL" — esa solo funciona dentro de Render
5. Desde terminal local, ejecutar una sola vez:
   ```bash
   DATABASE_URL="<pegar External Database URL aquí>" python migrate_data.py
   ```
6. En el dashboard del servicio `ct-app` → hacer clic en **"Manual Deploy" → "Deploy latest commit"** para lanzar un redeploy ahora que las tablas existen
7. Render asigna una URL pública tipo `https://ct-app.onrender.com`  
   Compartir esa URL con los supervisores

---

## 9. Consideraciones de seguridad

- Las credenciales (`AUTH_USER`, `AUTH_PASS`) se almacenan **únicamente** como variables de entorno en Render, nunca en el código ni en el repositorio público de GitHub. El código valida su presencia al arrancar y falla con error si alguna falta.
- La `DATABASE_URL` es inyectada automáticamente por Render desde la BD del mismo proyecto.
- Render provee HTTPS automáticamente — el Basic Auth viaja cifrado en tránsito.
- El plan gratuito de Render pausa el servicio tras 15 min de inactividad; el primer acceso puede tardar ~30 segundos en despertar (comportamiento normal, no un error).

---

## 10. Criterios de éxito

- [ ] La app responde en la URL pública de Render
- [ ] El navegador pide usuario y contraseña al entrar
- [ ] Acceder con credenciales incorrectas devuelve 401
- [ ] Se pueden crear, ver y eliminar registros (DELETE también requiere auth)
- [ ] El export de Excel funciona
- [ ] El dashboard muestra estadísticas correctas
- [ ] Los folios se generan sin duplicados bajo uso normal
- [ ] El servicio arranca correctamente (sin errores por variables de entorno faltantes)
