"""Generador del reporte informativo (PDF) del operativo de domicilios.
Se usa desde el botón "Descargar PDF" del tablero. Recibe los registros del
periodo y la configuración de polígonos; devuelve los bytes del PDF."""
import io
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, String

DARK = colors.HexColor('#2c3e50'); GREY = colors.HexColor('#eef1f4'); LGREY = colors.HexColor('#d9dee6')


def construir_reporte(rows, asignados, cubiertos, colores, fecha_txt):
    """rows: lista de dicts con 'equipo','uso','problematica'.
    asignados: {'1':[..],...}; cubiertos: [1,2,..]; colores: {'1':'#..',...}."""
    poly_team = {int(p): t for t, ps in asignados.items() for p in ps}
    allp = sorted(poly_team); total = len(allp) or 1
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
    CB = ParagraphStyle('cb', parent=st['Normal'], fontSize=8.5, leading=10.5, textColor=colors.white, fontName='Helvetica-Bold')
    CBc = ParagraphStyle('cbc', parent=CB, alignment=1)
    NOTE = ParagraphStyle('n', parent=st['Normal'], fontSize=8.5, textColor=colors.HexColor('#7f8c8d'), leading=11)

    def P(t, s=C):
        return Paragraph(escape(str(t if t not in (None, '') else '—')), s)

    def mini(titulo, data):
        body = [[P(titulo, CB), P('Actas', CBc)]]
        for k, v in sorted(data.items(), key=lambda x: -x[1]):
            body.append([P(k), P(v, Cc)])
        t = Table(body, colWidths=[5.4 * cm, 1.8 * cm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GREY]),
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
                       ' · ' + str(len(rows)) + ' amonestaciones · ' + str(ncov) + ' de ' + str(total) +
                       ' polígonos cubiertos (' + str(round(ncov / total * 100)) + '%) · faltan ' + str(total - ncov), SUB))
    S.append(Spacer(1, 5))
    S.append(Paragraph('Resumen del día', H2))
    resumen = Table([[mini('Por equipo', por_eq), mini('Por problemática', por_prob), mini('Por uso', por_uso)]],
                    colWidths=[7.7 * cm, 7.7 * cm, 7.7 * cm])
    resumen.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(resumen)

    covered_sorted = [p for p in allp if p in cov]
    if covered_sorted:
        S.append(Paragraph('Polígonos cubiertos', H2))
        celdas = []
        for p in covered_sorted:
            t = poly_team[p]; d = Drawing(80, 52)
            d.add(Rect(2, 2, 76, 48, rx=6, ry=6, fillColor=tcol.get(t, DARK), strokeColor=colors.white, strokeWidth=1.5))
            d.add(String(40, 29, 'R%d' % p, fontName='Helvetica-Bold', fontSize=17, fillColor=colors.white, textAnchor='middle'))
            d.add(String(40, 11, tname.get(t, ''), fontName='Helvetica', fontSize=7.5, fillColor=colors.white, textAnchor='middle'))
            celdas.append(d)
        # máximo 8 por fila
        for i in range(0, len(celdas), 8):
            fila = celdas[i:i + 8]
            g = Table([fila], colWidths=[2.9 * cm] * len(fila))
            g.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
            S.append(g)

    S.append(Paragraph('Avance del operativo', H2))
    pct = ncov / total
    bar = Drawing(300, 24)
    bar.add(Rect(0, 4, 232, 15, rx=4, ry=4, fillColor=LGREY, strokeColor=None))
    bar.add(Rect(0, 4, 232 * pct, 15, rx=4, ry=4, fillColor=colors.HexColor('#27ae60'), strokeColor=None))
    bar.add(String(240, 8, '%d/%d (%d%%)' % (ncov, total, round(pct * 100)), fontName='Helvetica-Bold', fontSize=10, fillColor=DARK))
    tbody = [[P('Equipo', CB), P('Hoy', CBc), P('Asignados', CBc), P('Faltan', CBc)]]
    bold = ParagraphStyle('b', parent=C, fontName='Helvetica-Bold'); boldc = ParagraphStyle('bc', parent=Cc, fontName='Helvetica-Bold')
    for k in sorted(asignados):
        ps = [int(x) for x in asignados[k]]; cub = len([p for p in ps if p in cov])
        tbody.append([P(tname[k]), P(cub, Cc), P(len(ps), Cc), P(len(ps) - cub, Cc)])
    tbody.append([P('TOTAL', bold), P(ncov, boldc), P(total, boldc), P(total - ncov, boldc)])
    tav = Table(tbody, colWidths=[3.4 * cm, 1.7 * cm, 2.4 * cm, 1.8 * cm])
    tav.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GREY]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe6ec')), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    cols = 10; gceld = []
    for p in allp:
        t = poly_team[p]; c = p in cov; d = Drawing(38, 23)
        d.add(Rect(1, 1, 36, 21, rx=3, ry=3, fillColor=(tcol.get(t, DARK) if c else colors.HexColor('#eef1f4')),
                   strokeColor=(colors.white if c else LGREY), strokeWidth=1))
        d.add(String(19, 8, 'R%d' % p, fontName='Helvetica-Bold', fontSize=8,
                     fillColor=(colors.white if c else colors.HexColor('#95a5a6')), textAnchor='middle'))
        gceld.append(d)
    filas = [gceld[i:i + cols] for i in range(0, len(gceld), cols)]
    for f in filas:
        while len(f) < cols:
            f.append('')
    rej = Table(filas, colWidths=[1.45 * cm] * cols)
    rej.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    izq = Table([[bar], [Spacer(1, 6)], [tav]], colWidths=[11 * cm]); izq.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    der = Table([[Paragraph('Mapa de avance — %d polígonos (los grises faltan)' % total,
        ParagraphStyle('x', parent=NOTE, fontName='Helvetica-Bold', textColor=DARK))], [rej]], colWidths=[15 * cm])
    der.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    comp = Table([[izq, der]], colWidths=[11.5 * cm, 15.3 * cm]); comp.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(comp)
    doc.build(S)
    buf.seek(0)
    return buf.read()
