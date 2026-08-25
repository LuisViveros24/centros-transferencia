# Relación Equipo / Polígonos / Color

**Operativo de Orden y Limpieza — Centro de Torreón**
Dirección General de Servicios Públicos Municipales · Dirección de Limpieza (DGSPM)
Fuente oficial: `Relacion_Equipo_Poligonos_Color.pdf` (Torreón, Coahuila, 20 de agosto de 2026).

Esta es la relación vigente que usa la app (constante `POLY_ASIGNADOS` en `app.py`,
config `poligonos_asignados` en BD, y campo `team` de `mapa_poligonos.json`).
El color de cada equipo es el mismo con que aparecen sus polígonos en el mapa (KML).

| Equipo | Integrantes | Polígonos asignados (en orden de avance) | N.º | Color | Hex |
|--------|-------------|------------------------------------------|-----|-------|-----|
| Equipo 1 | César Alvarado, Rafael Moisés, Cristina Estrada (3) | R2, R4, R12, R15, R16, R20, R26, R31 | 8 | Azul | `#2980b9` |
| Equipo 2 | Alberto Adame Martínez, Itzel García (2) | R1, R3, R6, R9, R21, R27, R32, R39 | 8 | Verde | `#27ae60` |
| Equipo 3 | José Guajardo, César Crispín, Dulce Pérez (3) | R5, R8, R7, R11, R14, R17, R18, R33 | 8 | Naranja | `#e67e22` |
| Equipo 4 | Abraham Álvarez, Luis Viveros (2) | R10, R13, R19, R28, R29, R34, R40, R41 | 8 | Morado | `#8e44ad` |
| Equipo 5 | Ernesto Escalera, Salvador García (2) | R24, R25, R30, R37, R36, R35, R38, R42 | 8 | Rojo | `#e74c3c` |
| **TOTAL** | **12 integrantes** | **40 polígonos (R1–R42; no existen R22 ni R23)** | **40** | **5 colores** | |

## Dónde vive esto en la app

- **`app.py` → `POLY_ASIGNADOS`**: valor por defecto (se usa si la BD no lo tiene).
- **`app.py` → `POLY_COLORS`**: `{'1':'#2980b9','2':'#27ae60','3':'#e67e22','4':'#8e44ad','5':'#e74c3c'}`.
- **BD, tabla `config`, clave `poligonos_asignados`**: valor efectivo (gana sobre el
  default del código). Si se cambia la relación, **hay que actualizar también este
  registro**, no solo el código.
- **`mapa_poligonos.json` → campo `team` por polígono**: define de qué color se pinta
  cada polígono en el mapa del tablero y del PDF. Debe coincidir con `POLY_ASIGNADOS`.

## Archivos fuente (en esta carpeta)

- `Relacion_Equipo_Poligonos_Color.pdf` / `.docx` — tabla oficial.
- `Mapa_Franjas_Horizontales.png` — mapa de referencia.
- `Rutas_y_Equipos.kmz` — geometría y colores de los polígonos (Google Earth/Maps).
