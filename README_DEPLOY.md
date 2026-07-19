# Centros de Transferencia — Guía de Despliegue en Render.com

Esta guía explica cómo poner la app en internet para que los supervisores
puedan acceder desde cualquier navegador.

---

## Requisitos previos

- Cuenta de GitHub con el repositorio `centros-transferencia` subido
- Cuenta en [Render.com](https://render.com) (gratuita)

---

## Paso 1 — Crear cuenta en Render y conectar GitHub

1. Ir a [render.com](https://render.com) → **Sign Up**
2. Seleccionar **Continue with GitHub**
3. Autorizar a Render el acceso al repositorio `centros-transferencia`

---

## Paso 2 — Crear el Blueprint (BD + Web Service automáticos)

1. En el dashboard de Render → **New +** → **Blueprint**
2. Seleccionar el repositorio `centros-transferencia`
3. Render detecta el archivo `render.yaml` y muestra un resumen:
   - Un **Web Service** llamado `ct-app` (plan Free, región Oregon)
   - Una **Base de datos PostgreSQL** llamada `ct-db` (plan Free, región Oregon)
4. Hacer clic en **Apply**

> ⚠️ **El primer deploy fallará** con un error de base de datos — esto es **normal y esperado**.
> Las tablas todavía no existen. Continúa con los siguientes pasos antes de
> preocuparte por el error.

---

## Paso 3 — Agregar las credenciales de acceso

1. En el dashboard de Render → seleccionar el servicio **ct-app**
2. Ir a la pestaña **Environment**
3. Hacer clic en **Add Environment Variable** y agregar dos entradas:

   | Key | Value |
   |-----|-------|
   | `AUTH_USER` | `PGA2627` |
   | `AUTH_PASS` | `Limpie$a2627` |

4. Hacer clic en **Save Changes**

> ℹ️ Estas credenciales nunca aparecen en el código ni en GitHub.
> Solo existen dentro del ambiente seguro de Render.

---

## Paso 4 — Obtener la URL de conexión externa de la base de datos

1. En el dashboard de Render → seleccionar el servicio **ct-db**
2. Ir a la pestaña **Connections**
3. Copiar el campo **"External Database URL"**
   - Empieza con `postgresql://...`
   - ⚠️ **No copiar** la "Internal Database URL" — esa solo funciona dentro de Render

---

## Paso 5 — Crear las tablas (una sola vez)

Desde una terminal en tu computadora, ejecutar:

```bash
DATABASE_URL="<pegar aquí la External Database URL>" python migrate_data.py
```

Reemplazar `<pegar aquí la External Database URL>` con lo que copiaste en el Paso 4.

Resultado esperado:
```
Conectando a PostgreSQL...
Creando tabla registros...
Creando tabla config...
Insertando contador de folio inicial...

✓ Esquema creado correctamente en PostgreSQL.
  Puedes hacer un Manual Deploy en Render ahora.
```

---

## Paso 6 — Redeploy manual

1. En el dashboard de Render → seleccionar el servicio **ct-app**
2. Hacer clic en **Manual Deploy** → **Deploy latest commit**
3. Esperar ~2 minutos a que termine el deploy
4. El estado cambiará a **Live** ✅

---

## Paso 6.5 — Roles y mapa de colonias (opcional)

**Roles admin / captura.** Por defecto el usuario `AUTH_USER` tiene acceso total.
Para separar en dos roles (captura = solo Entrada/Salida; admin = todo), en Render →
servicio **ct-app** → **Environment** → **Add Environment Variable**, agregar:

| Key | Value |
|-----|-------|
| `ADMIN_USER` | (el usuario admin que elijas) |
| `ADMIN_PASS` | (su contraseña) |

Con esas variables, `AUTH_USER` queda restringido a captura y `ADMIN_USER` ve
Dashboard, Historial, exportación y eliminación. Sin ellas, todo sigue como antes.

**Mapa de colonias.** El mapa del Dashboard necesita geocodificar las colonias una
vez. Desde tu terminal (tarda ~15 min, es reanudable — puedes repetirlo cuando haya
colonias nuevas):

```bash
DATABASE_URL="<pegar aquí la External Database URL>" python geocode_colonias.py
```

Hasta correrlo, el mapa muestra un mensaje de "sin colonias ubicadas". La tabla
`colonias_geo` que usa ya la crea `migrate_data.py` en el Paso 5.

---

## Paso 7 — Compartir la URL con los supervisores

1. En la página del servicio `ct-app` en Render, copiar la URL pública
   - Ejemplo: `https://ct-app.onrender.com`
2. Enviar esa URL a los supervisores

Los supervisores entrarán al link, el navegador pedirá usuario y contraseña,
y podrán usar la app normalmente.

---

## Notas importantes

- **Primer acceso lento:** El plan gratuito de Render pausa el servicio tras
  15 minutos de inactividad. El primer acceso después de una pausa tarda ~30 segundos
  en despertar — esto es normal, no un error.

- **HTTPS incluido:** Render provee HTTPS automáticamente. La contraseña viaja
  cifrada.

- **Actualizaciones futuras:** Cada vez que se suba código nuevo a GitHub
  (`git push`), Render desplegará automáticamente la nueva versión.
