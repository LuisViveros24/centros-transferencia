"""Generador del reporte informativo (PDF) del operativo de domicilios.
Se usa desde el botón "Descargar PDF" del tablero."""
import io, os, json
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, String, Polygon as RLPolygon

DARK = colors.HexColor('#2c3e50'); GREY = colors.HexColor('#eef1f4'); LGREY = colors.HexColor('#d9dee6')


def _load_geo():
    try:
        with open(os.path.join(os.path.dirname(__file__), 'mapa_poligonos.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def construir_reporte(rows, asignados, cubiertos, colores, fecha_txt):
    poly_team = {int(p): t for t, ps in asignados.items() for p in ps}
    allp = sorted(poly_team); total_poly = len(allp) or 1
    cov = set(int(x) for x in cubiertos)
    tcol = {k: colors.HexColor(v) for k, v in colores.items()}
    tname = {k: 'Equipo ' + k for k in asignados}

    por_eq = {}; por_prob = {}; por_uso = {}
    for r in rows:
        k = (r.get('equipo') or '—').split(' · ')[0]
        por_eq[k] = por_eq.get(k, 0) + 1
        por_uso[r.get('uso') or '—'] = por_uso.get(r.get('uso') or '—', 0) + 1
        for p in (r.get('problematica') or '').split(','):
            p = p.strip().split(':')[0].strip()
            if p:
                por_prob[p] = por_prob.get(p, 0) + 1

    st = getSampleStyleSheet()
    H1 = ParagraphStyle('h1', parent=st['Title'], fontSize=16, textColor=DARK, spaceAfter=2)
    SUB = ParagraphStyle('s', parent=st['Normal'], fontSize=9.5, textColor=colors.HexColor('#7f8c8d'), spaceAfter=2)
    H2 = ParagraphStyle('h2', parent=st['Heading2'], fontSize=12.5, textColor=DARK, spaceBefore=7, spaceAfter=3)
    C = ParagraphStyle('c', parent=st['Normal'], fontSize=8.5, leading=10.5)
    Cc = ParagraphStyle('cc', parent=C, alignment=1)
    Cb = ParagraphStyle('cb2', parent=C, fontName='Helvetica-Bold')
    Ccb = ParagraphStyle('ccb', parent=Cc, fontName='Helvetica-Bold')
    CB = ParagraphStyle('cb', parent=st['Normal'], fontSize=8.5, leading=10.5, textColor=colors.white, fontName='Helvetica-Bold')
    CBc = ParagraphStyle('cbc', parent=CB, alignment=1)
    NOTE = ParagraphStyle('n', parent=st['Normal'], fontSize=8.5, textColor=colors.HexColor('#7f8c8d'), leading=11)

    def P(t, s=C):
        return Paragraph(escape(str(t if t not in (None, '') else '—')), s)

    def mini(titulo, data):
        items = sorted(data.items(), key=lambda x: -x[1])
        body = [[P(titulo, CB), P('Actas', CBc)]]
        for k, v in items:
            body.append([P(k), P(v, Cc)])
        body.append([P('Total', Cb), P(sum(v for _, v in items), Ccb)])
        t = Table(body, colWidths=[5.4 * cm, 1.8 * cm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GREY]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe6ec')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), topMargin=1.0 * cm, bottomMargin=0.9 * cm,
                            leftMargin=1.3 * cm, rightMargin=1.3 * cm, title='Reporte informativo — Operativo')
    S = []
    S.append(Paragraph('Operativo de Orden y Limpieza — Centro de Torreón', H1))
    S.append(Paragraph('Reporte informativo · ' + fecha_txt + ' · Dirección de Limpieza (DGSPM)', SUB))
    ncov = len([p for p in allp if p in cov])
    S.append(Paragraph('Generado el ' + datetime.now().strftime('%d/%m/%Y %H:%M') +
                       ' · ' + str(len(rows)) + ' amonestaciones · ' + str(ncov) + ' de ' + str(total_poly) +
                       ' polígonos cubiertos (' + str(round(ncov / total_poly * 100)) + '%) · faltan ' + str(total_poly - ncov), SUB))
    S.append(Spacer(1, 5))
    S.append(Paragraph('Resumen del día', H2))
    resumen = Table([[mini('Por equipo', por_eq), mini('Por problemática', por_prob), mini('Por uso', por_uso)]],
                    colWidths=[7.7 * cm, 7.7 * cm, 7.7 * cm])
    resumen.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(resumen)

    # Avance del operativo: barra + tabla por equipo (izq) + MAPA REAL (der)
    S.append(Paragraph('Avance del operativo', H2))
    pct = ncov / total_poly
    bar = Drawing(300, 24)
    bar.add(Rect(0, 4, 232, 15, rx=4, ry=4, fillColor=LGREY, strokeColor=None))
    bar.add(Rect(0, 4, 232 * pct, 15, rx=4, ry=4, fillColor=colors.HexColor('#27ae60'), strokeColor=None))
    bar.add(String(240, 8, '%d/%d (%d%%)' % (ncov, total_poly, round(pct * 100)), fontName='Helvetica-Bold', fontSize=10, fillColor=DARK))
    tbody = [[P('Equipo', CB), P('Hoy', CBc), P('Asignados', CBc), P('Faltan', CBc)]]
    for k in sorted(asignados):
        ps = [int(x) for x in asignados[k]]; cub = len([p for p in ps if p in cov])
        tbody.append([P(tname[k]), P(cub, Cc), P(len(ps), Cc), P(len(ps) - cub, Cc)])
    tbody.append([P('TOTAL', Cb), P(ncov, Ccb), P(total_poly, Ccb), P(total_poly - ncov, Ccb)])
    tav = Table(tbody, colWidths=[3.4 * cm, 1.7 * cm, 2.4 * cm, 1.8 * cm])
    tav.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GREY]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe6ec')), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))

    geo = _load_geo()
    mapa = _mapa_drawing(geo, cov, tcol, 340) if geo and geo.get('polys') else _grid_fallback(allp, poly_team, cov, tcol)

    izq = Table([[bar], [Spacer(1, 6)], [tav]], colWidths=[11 * cm]); izq.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    der = Table([[Paragraph('Mapa del operativo — coloreados = cubiertos · grises = faltan',
        ParagraphStyle('x', parent=NOTE, fontName='Helvetica-Bold', textColor=DARK))], [mapa]], colWidths=[12.4 * cm])
    der.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    comp = Table([[izq, der]], colWidths=[13.5 * cm, 12.8 * cm]); comp.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(comp)
    doc.build(S)
    buf.seek(0)
    return buf.read()


def _mapa_drawing(geo, cov, tcol, target_w=430):
    sc = target_w / float(geo['w']); dw = target_w; dh = geo['h'] * sc
    d = Drawing(dw, dh)
    for p in geo['polys']:
        r = int(p['r']); c = r in cov
        fill = tcol.get(p['team'], DARK) if c else colors.HexColor('#e3e7ec')
        pts = []
        for (x, y) in p['pts']:
            pts += [x * sc, dh - y * sc]
        d.add(RLPolygon(points=pts, fillColor=fill, strokeColor=colors.white, strokeWidth=0.8, fillOpacity=(0.9 if c else 0.75)))
        cx = sum(pt[0] for pt in p['pts']) / len(p['pts']) * sc
        cy = dh - sum(pt[1] for pt in p['pts']) / len(p['pts']) * sc
        d.add(String(cx, cy - 3, 'R%d' % r, fontName='Helvetica-Bold', fontSize=6.5,
                     fillColor=(colors.white if c else colors.HexColor('#8a94a3')), textAnchor='middle'))
    return d


def _grid_fallback(allp, poly_team, cov, tcol):
    cols = 10; gceld = []
    for p in allp:
        c = p in cov; d = Drawing(38, 23)
        d.add(Rect(1, 1, 36, 21, rx=3, ry=3, fillColor=(tcol.get(poly_team.get(p), DARK) if c else colors.HexColor('#eef1f4')),
                   strokeColor=(colors.white if c else LGREY), strokeWidth=1))
        d.add(String(19, 8, 'R%d' % p, fontName='Helvetica-Bold', fontSize=8,
                     fillColor=(colors.white if c else colors.HexColor('#95a5a6')), textAnchor='middle'))
        gceld.append(d)
    filas = [gceld[i:i + cols] for i in range(0, len(gceld), cols)]
    for f in filas:
        while len(f) < cols:
            f.append('')
    t = Table(filas, colWidths=[1.45 * cm] * cols)
    t.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    return t
