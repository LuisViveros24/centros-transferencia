"""
geocode_colonias.py — Llena la tabla colonias_geo con coordenadas de las
colonias de origen usando Nominatim (OpenStreetMap, gratis y sin API key).

Respeta el límite de 1 consulta por segundo de Nominatim. Es REANUDABLE:
solo procesa colonias que aún no están en el caché, así que puedes correrlo
las veces que quieras (por ejemplo cuando aparezcan colonias nuevas).

Solo guarda como 'ok' las colonias que Nominatim ubica claramente dentro
del área de Torreón, a nivel de colonia/barrio (no la ciudad entera). Las
que no se pueden ubicar quedan como 'no_encontrada' y no aparecen en el mapa.

Uso (una sola vez, o cuando haya colonias nuevas):
    DATABASE_URL="postgresql://..." python3 geocode_colonias.py
"""
import os
import time
import json
import unicodedata
import urllib.parse
import urllib.request
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise SystemExit(
        'ERROR: define DATABASE_URL antes de correr este script.\n'
        'Ejemplo:\n'
        '  DATABASE_URL="postgresql://user:pass@host/db" python3 geocode_colonias.py'
    )

# Caja aproximada de Torreón, Coahuila (lon_min, lat_min, lon_max, lat_max)
BBOX = (-103.55, 25.45, -103.30, 25.62)
# viewbox de Nominatim: x1,y1,x2,y2 (esquina sup-izq, esquina inf-der)
VIEWBOX = '{},{},{},{}'.format(BBOX[0], BBOX[3], BBOX[2], BBOX[1])
USER_AGENT = 'CentrosTransferencia-Torreon/1.0 (geocodificador de colonias)'


def _norm(s):
    """Minúsculas sin acentos, para comparar nombres de forma robusta."""
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def geocode(sample):
    """Devuelve (lat, lng) si la colonia se ubica claramente, o None.

    OSM casi no tiene las colonias de Torreón como polígonos: suele
    hacer match con calles del mismo nombre. Aceptamos el resultado
    solo si (a) cae dentro del área de Torreón y (b) el nombre de la
    colonia aparece de verdad en el resultado — así una calle homónima
    sirve de ubicación aproximada, pero se descartan los 'fallback'
    que Nominatim devuelve sin relación con el nombre buscado."""
    q = urllib.parse.urlencode({
        'q': sample + ', Torreón, Coahuila, México',
        'format': 'json', 'limit': '1', 'countrycodes': 'mx',
        'addressdetails': '1', 'viewbox': VIEWBOX, 'bounded': '1',
    })
    url = 'https://nominatim.openstreetmap.org/search?' + q
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    if not data:
        return None
    r = data[0]
    lat, lon = float(r['lat']), float(r['lon'])
    if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
        return None  # fuera del área de Torreón
    if _norm(sample) not in _norm(r.get('display_name', '')):
        return None  # el resultado no corresponde al nombre de la colonia
    return lat, lon


def main():
    print('Conectando a PostgreSQL...')
    conn = psycopg2.connect(DATABASE_URL)

    with conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS colonias_geo (
                    colonia_norm TEXT PRIMARY KEY,
                    lat          REAL,
                    lng          REAL,
                    estado       TEXT NOT NULL,
                    creado_en    TIMESTAMP DEFAULT NOW()
                )
            ''')

    with conn.cursor() as cur:
        cur.execute('''
            SELECT LOWER(TRIM(colonia)) norm, MAX(TRIM(colonia)) sample
            FROM registros
            WHERE tipo='ENTRADA' AND colonia IS NOT NULL AND TRIM(colonia) != ''
            GROUP BY 1
        ''')
        colonias = cur.fetchall()
        cur.execute('SELECT colonia_norm FROM colonias_geo')
        ya_cacheadas = {row[0] for row in cur.fetchall()}

    pendientes = [(n, s) for n, s in colonias if n not in ya_cacheadas]
    print('{} colonias distintas, {} por geocodificar (~{} min a 1/seg)...'.format(
        len(colonias), len(pendientes), max(1, len(pendientes) // 60)))

    ok = falla = 0
    for i, (norm, sample) in enumerate(pendientes, 1):
        try:
            res = geocode(sample)
        except Exception as e:
            # Error de red: no se guarda, se reintenta en la próxima corrida.
            print('  [{}/{}] {!r}: error de red ({}); se reintentará luego'.format(
                i, len(pendientes), sample, e))
            time.sleep(1)
            continue

        if res:
            lat, lng = res
            estado = 'ok'
            ok += 1
        else:
            lat = lng = None
            estado = 'no_encontrada'
            falla += 1

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO colonias_geo (colonia_norm, lat, lng, estado) '
                    'VALUES (%s,%s,%s,%s) ON CONFLICT (colonia_norm) DO NOTHING',
                    (norm, lat, lng, estado))

        if i % 25 == 0:
            print('  [{}/{}] ubicadas={} no_encontradas={}'.format(
                i, len(pendientes), ok, falla))
        time.sleep(1)  # respetar el límite de 1 req/seg de Nominatim

    print('\n✓ Listo. {} ubicadas, {} no encontradas (de {} nuevas).'.format(
        ok, falla, len(pendientes)))
    print('  El mapa del Dashboard ya mostrará las colonias ubicadas.')
    conn.close()


if __name__ == '__main__':
    main()
