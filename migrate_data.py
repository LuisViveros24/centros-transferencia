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
