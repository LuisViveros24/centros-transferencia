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
                    nombre    TEXT,
                    telefono  TEXT,
                    colonia   TEXT,
                    vehiculo  TEXT,
                    placa     TEXT,
                    m3        REAL DEFAULT 0,
                    obs       TEXT,
                    creado_en TIMESTAMP DEFAULT NOW()
                )
            ''')
            # Agregar columna nombre si la tabla ya existía sin ella
            cur.execute('''
                ALTER TABLE registros ADD COLUMN IF NOT EXISTS nombre TEXT
            ''')
            # Agregar columna calle si la tabla ya existía sin ella
            cur.execute('''
                ALTER TABLE registros ADD COLUMN IF NOT EXISTS calle TEXT
            ''')
            # Agregar columna telefono si la tabla ya existía sin ella
            cur.execute('''
                ALTER TABLE registros ADD COLUMN IF NOT EXISTS telefono TEXT
            ''')
            print('Creando tabla config...')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    clave TEXT PRIMARY KEY,
                    valor TEXT
                )
            ''')
            print('Creando tabla colonias_geo (caché de geocodificación)...')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS colonias_geo (
                    colonia_norm TEXT PRIMARY KEY,
                    lat          REAL,
                    lng          REAL,
                    estado       TEXT NOT NULL,
                    creado_en    TIMESTAMP DEFAULT NOW()
                )
            ''')
            print('Creando tabla domicilios (control de predios)...')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS domicilios (
                    id              SERIAL PRIMARY KEY,
                    folio           TEXT NOT NULL,
                    fecha           DATE NOT NULL,
                    direccion       TEXT,
                    uso             TEXT,
                    nombre_comercio TEXT,
                    estado          TEXT,
                    problematica    TEXT,
                    obs             TEXT,
                    creado_en       TIMESTAMP DEFAULT NOW()
                )
            ''')
            # Columnas agregables si la tabla domicilios ya existía sin ellas
            # (facilita ampliar el formulario sin recrear la tabla).
            for _col, _tipo in (('obs','TEXT'), ('nombre_comercio','TEXT'),
                                ('equipo','TEXT'), ('plazo_horas','INTEGER'),
                                ('folio_acta','TEXT'), ('accion','TEXT'),
                                ('lat','REAL'), ('lng','REAL'),
                                ('foto_pdf','BYTEA'),
                                ('cumplido','BOOLEAN'), ('cumplido_en','TIMESTAMP'),
                                ('cumplido_obs','TEXT'), ('cumplido_por','TEXT')):
                print(f'  · columna domicilios.{_col}')
                cur.execute(f'ALTER TABLE domicilios ADD COLUMN IF NOT EXISTS {_col} {_tipo}')
            print('Insertando contador de folio inicial...')
            cur.execute(
                "INSERT INTO config VALUES ('folio_base', '1') ON CONFLICT DO NOTHING"
            )
            print('Insertando contador de folio de domicilios...')
            cur.execute(
                "INSERT INTO config VALUES ('folio_dom', '1') ON CONFLICT DO NOTHING"
            )
    print('\n✓ Esquema creado correctamente en PostgreSQL.')
    print('  Puedes hacer un Manual Deploy en Render ahora.')
finally:
    conn.close()
