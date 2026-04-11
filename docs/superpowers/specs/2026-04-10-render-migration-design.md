# Diseño: Migración de ct_app_mac a Render.com con PostgreSQL

**Fecha:** 2026-04-10  
**Proyecto:** Centros de Transferencia — Control de Viajes  
**Repositorio:** https://github.com/LuisViveros24/centros-transferencia.git

---

## 1. Contexto y Objetivo

La aplicación Flask `ct_app_mac` actualmente corre en una máquina local con SQLite, accesible solo en red local. El objetivo es migrarla a Render.com con PostgreSQL para que cualquier persona con el link pueda acceder desde cualquier navegador, con protección de contraseña.

### Estado actual
- Flask + SQLite (2 tablas: `registros` y `config`)
- 5 rutas API + exportación Excel
- Sin autenticación
- 0 registros existentes (DB vacía, solo contador de folio en 1)

### Estado objetivo
- Flask + PostgreSQL en Render.com
- Misma lógica y rutas sin cambios
- HTTP Basic Auth (un usuario)
- Accesible públicamente vía URL de Render

---

## 2. Arquitectura

```
GitHub (LuisViveros24/centros-transferencia)
        │  push → deploy automático
        ▼
Render Web Service
  └── Python / Gunicorn / app.py
        │
        ▼
  Render PostgreSQL (plan gratuito)
  └── DB: centros_transferencia
        tablas: registros, config
```

### Variables de entorno en Render

| Variable       | Origen                                 |
|----------------|----------------------------------------|
| `DATABASE_URL` | Auto-inyectada por Render desde la BD  |
| `AUTH_USER`    | Manual en dashboard de Render          |
| `AUTH_PASS`    | Manual en dashboard de Render          |

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

### 4.2 Configuración de conexión

```python
DATABASE_URL = os.environ.get('DATABASE_URL')
AUTH_USER    = os.environ.get('AUTH_USER', 'PGA2627')
AUTH_PASS    = os.environ.get('AUTH_PASS', 'Limpie$a2627')
```

### 4.3 Función `get_db()`

```python
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn
```

Las queries se ejecutan con `cursor_factory=psycopg2.extras.RealDictCursor` para mantener acceso por nombre de columna (`row['campo']`), idéntico al comportamiento de `sqlite3.Row`.

### 4.4 Función `init_db()`

Cambios de sintaxis SQL:
- `INTEGER PRIMARY KEY AUTOINCREMENT` → `SERIAL PRIMARY KEY`
- `TEXT DEFAULT (datetime('now','localtime'))` → `TIMESTAMP DEFAULT NOW()`
- `INSERT OR IGNORE INTO config VALUES (...)` → `INSERT INTO config VALUES (...) ON CONFLICT DO NOTHING`

### 4.5 Placeholders SQL

Reemplazar todos los `?` por `%s` en cada query (único cambio repetido en el código).

### 4.6 Historial 14 días — aritmética de fechas

```sql
-- SQLite (antes):
WHERE fecha >= date(?, 'start of day', '-13 days')

-- PostgreSQL (después):
WHERE fecha >= (%s::date - INTERVAL '13 days')
```

### 4.7 Folio con bloqueo de fila

Para evitar folios duplicados con acceso concurrente:

```sql
SELECT valor FROM config WHERE clave='folio_base' FOR UPDATE
```

### 4.8 HTTP Basic Auth

Decorador aplicado a **todas** las rutas (`/`, `/api/registros`, `/api/dashboard`, `/api/export/excel`):

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

psycopg2 no usa context manager de la misma forma que sqlite3. El patrón es:

```python
conn = get_db()
try:
    with conn:           # maneja commit/rollback
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
finally:
    conn.close()
```

### 4.10 Punto de entrada

```python
if __name__ == '__main__':
    init_db()
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
    databaseName: centros_transferencia
```

---

## 7. `migrate_data.py`

Script de ejecución única. Dado que la base de datos SQLite está vacía (0 registros), su función es:

1. Leer `DATABASE_URL` del entorno
2. Conectar a PostgreSQL
3. Crear las tablas `registros` y `config` si no existen
4. Insertar el valor inicial del contador de folio (`folio_base = 1`)

No migra registros porque no hay ninguno.

---

## 8. `README_DEPLOY.md` — Pasos de despliegue

1. Crear cuenta en [render.com](https://render.com)
2. Conectar cuenta de GitHub
3. New → Blueprint → seleccionar repositorio `centros-transferencia`  
   Render detecta `render.yaml` y crea automáticamente la BD y el web service
4. En el dashboard del servicio → Environment → agregar:
   - `AUTH_USER` = `PGA2627`
   - `AUTH_PASS` = `Limpie$a2627`
5. Desde terminal local, con `DATABASE_URL` exportada:
   ```bash
   python migrate_data.py
   ```
6. Render asigna una URL pública tipo `https://ct-app.onrender.com`  
   Compartir esa URL con los supervisores

---

## 9. Consideraciones de seguridad

- Las credenciales (`AUTH_USER`, `AUTH_PASS`) se almacenan como variables de entorno en Render, nunca en el código ni en el repositorio
- La `DATABASE_URL` es inyectada automáticamente por Render
- El plan gratuito de Render pausa el servicio tras 15 min de inactividad; el primer acceso puede tardar ~30 segundos en despertar
- Se recomienda usar HTTPS (Render lo provee automáticamente) para que el Basic Auth esté cifrado en tránsito

---

## 10. Criterios de éxito

- [ ] La app responde en la URL pública de Render
- [ ] El navegador pide usuario y contraseña al entrar
- [ ] Se pueden crear, ver y eliminar registros
- [ ] El export de Excel funciona
- [ ] El dashboard muestra estadísticas correctas
- [ ] Los folios se generan sin duplicados
