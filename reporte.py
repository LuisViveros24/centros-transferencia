"""Generador del reporte informativo (PDF) del operativo de domicilios.
Se usa desde el botón "Descargar PDF" del tablero."""
import io, os, json, re
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.graphics.shapes import Drawing, Rect, String, Polygon as RLPolygon
from reportlab.graphics.charts.piecharts import Pie

DARK = colors.HexColor('#2c3e50'); GREY = colors.HexColor('#eef1f4'); LGREY = colors.HexColor('#d9dee6')


def _load_geo():
    try:
        with open(os.path.join(os.path.dirname(__file__), 'mapa_poligonos.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def construir_reporte(rows, asignados, colores, fecha_txt, manzanas=None, cubiertas=None, seguimiento=None):
    poly_team = {int(p): t for t, ps in asignados.items() for p in ps}
    allp = sorted(poly_team); total_poly = len(allp) or 1
    mz = {int(k): int(v) for k, v in (manzanas or {}).items()}
    mc = {int(k): int(v) for k, v in (cubiertas or {}).items()}
    cov = set(p for p in allp if mz.get(p, 0) > 0 and mc.get(p, 0) >= mz.get(p, 0))
    encurso = [p for p in allp if 0 < mc.get(p, 0) < mz.get(p, 0)]
    tot_mz = sum(mz.get(p, 0) for p in allp) or 1
    cub_mz = sum(min(mc.get(p, 0), mz.get(p, 0)) for p in allp)
    pct_mz = cub_mz / tot_mz
    tcol = {k: colors.HexColor(v) for k, v in colores.items()}
    tname = {k: 'Equipo ' + k for k in asignados}

    por_eq = {}; por_prob = {}; por_uso = {}; multa_prob = {}
    for r in rows:
        k = (r.get('equipo') or '—').split(' · ')[0]
        por_eq[k] = por_eq.get(k, 0) + 1
        por_uso[r.get('uso') or 'Ambos'] = por_uso.get(r.get('uso') or 'Ambos', 0) + 1
        es_multa = (r.get('multa') is True) and (str(r.get('accion') or '').strip() == 'Amonestado')
        partes = [x.strip().split(':')[0].strip() for x in (r.get('problematica') or '').split(',') if x.strip()]
        for p in partes:
            por_prob[p] = por_prob.get(p, 0) + 1
        # Multas: una por caso, por su problemática principal (la primera del folio)
        if es_multa and partes:
            multa_prob[partes[0]] = multa_prob.get(partes[0], 0) + 1

    st = getSampleStyleSheet()
    H1 = ParagraphStyle('h1', parent=st['Title'], fontSize=16, textColor=DARK, spaceAfter=2)
    SUB = ParagraphStyle('s', parent=st['Normal'], fontSize=9.5, textColor=colors.HexColor('#7f8c8d'), spaceAfter=2)
    H2 = ParagraphStyle('h2', parent=st['Heading2'], fontSize=12.5, textColor=DARK, spaceBefore=4, spaceAfter=3)
    C = ParagraphStyle('c', parent=st['Normal'], fontSize=8.5, leading=10.5)
    Cc = ParagraphStyle('cc', parent=C, alignment=1)
    Cb = ParagraphStyle('cb2', parent=C, fontName='Helvetica-Bold')
    Ccb = ParagraphStyle('ccb', parent=Cc, fontName='Helvetica-Bold')
    CB = ParagraphStyle('cb', parent=st['Normal'], fontSize=8.5, leading=10.5, textColor=colors.white, fontName='Helvetica-Bold')
    CBc = ParagraphStyle('cbc', parent=CB, alignment=1)
    NOTE = ParagraphStyle('n', parent=st['Normal'], fontSize=8.5, textColor=colors.HexColor('#7f8c8d'), leading=11)

    def P(t, s=C):
        return Paragraph(escape(str(t if t not in (None, '') else '—')), s)

    PALETA = ['#3b82f6', '#27ae60', '#e67e22', '#8e44ad', '#e74c3c', '#14b8a6', '#eab308', '#f472b6', '#60a5fa', '#7f8c8d']

    def _cols(titulo, items):
        if titulo == 'Por equipo':
            r = []
            for k, _ in items:
                m = re.search(r'(\d+)', str(k)); r.append(colores.get(m.group(1), '#7f8c8d') if m else '#7f8c8d')
            return r
        return [PALETA[i % len(PALETA)] for i in range(len(items))]

    def mini(titulo, items, hx):
        body = [[P(titulo, CB), P('Cantidad', CBc)]]
        for i, (k, v) in enumerate(items):
            body.append([Paragraph('<font color="%s">\u25a0</font> %s' % (hx[i], escape(str(k))), C), P(v, Cc)])
        body.append([P('Total', Cb), P(sum(v for _, v in items), Ccb)])
        t = Table(body, colWidths=[5.2 * cm, 2.0 * cm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GREY]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe6ec')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5)]))
        return t

    def _pie(items, hx):
        d = Drawing(132, 88)
        pc = Pie(); pc.x = 30; pc.y = 6; pc.width = 72; pc.height = 72
        vals = [max(float(v), 0.0001) for _, v in items]; tot = sum(vals) or 1
        pc.data = vals
        pc.labels = [('%d%%' % round(v / tot * 100)) if v / tot >= 0.06 else '' for v in vals]
        pc.simpleLabels = 1
        pc.slices.labelRadius = 0.62
        pc.slices.strokeColor = colors.white; pc.slices.strokeWidth = 1.2
        pc.slices.fontName = 'Helvetica-Bold'; pc.slices.fontSize = 7; pc.slices.fontColor = colors.white
        for i in range(len(items)):
            pc.slices[i].fillColor = colors.HexColor(hx[i])
        d.add(pc); return d

    def columna(titulo, data):
        items = sorted(data.items(), key=lambda x: -x[1])
        hx = _cols(titulo, items)
        return Table([[mini(titulo, items, hx)], [Spacer(1, 3)], [_pie(items, hx)]],
                     colWidths=[7.6 * cm], style=[('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'TOP')])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), topMargin=1.0 * cm, bottomMargin=0.9 * cm,
                            leftMargin=1.3 * cm, rightMargin=1.3 * cm, title='Reporte informativo — Operativo')
    S = []
    S.append(Paragraph('Operativo de Orden y Limpieza — Centro de Torreón', H1))
    S.append(Paragraph('Reporte informativo · ' + fecha_txt + ' · Dirección de Limpieza (DGSPM)', SUB))
    ncov = len([p for p in allp if p in cov])
    S.append(Paragraph('Generado el ' + datetime.now().strftime('%d/%m/%Y %H:%M') +
                       ' · ' + str(len(rows)) + ' domicilios identificados · ' + str(ncov) + ' de ' + str(total_poly) +
                       ' polígonos cubiertos (' + str(round(ncov / total_poly * 100)) + '%) · faltan ' + str(total_poly - ncov), SUB))
    S.append(Spacer(1, 6))
    # Panel de KPIs (refleja el primer panel del tablero, sin "Multados")
    BIGN = ParagraphStyle('bign', parent=st['Title'], fontSize=20, textColor=DARK, alignment=1, spaceAfter=0, leading=22)
    KLBL = ParagraphStyle('klbl', parent=st['Normal'], fontSize=8, textColor=colors.HexColor('#7f8c8d'), alignment=1, leading=9)

    def kpi_box(num, label):
        inner = Table([[Paragraph(str(num), BIGN)], [Paragraph(label, KLBL)]], colWidths=[6.5 * cm])
        inner.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, LGREY), ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        return inner

    _acc = lambda v: sum(1 for r in rows if str(r.get('accion') or '').strip() == v)
    kpis = Table([[kpi_box(len(rows), 'Domicilios identificados'), kpi_box(_acc('Notificado'), 'Notificados'),
                   kpi_box(_acc('Amonestado'), 'Amonestados')]], colWidths=[8.0 * cm, 8.0 * cm, 8.0 * cm])
    kpis.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]))
    S.append(kpis)
    S.append(Spacer(1, 8))
    S.append(Paragraph('Resumen del día', H2))
    resumen = Table([[columna('Por equipo', por_eq), columna('Por problemática', por_prob), columna('Por uso', por_uso)]],
                    colWidths=[7.9 * cm, 7.9 * cm, 7.9 * cm])
    resumen.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(resumen)
    S.append(Paragraph('Nota: un solo predio puede presentar 2 o más problemáticas.', NOTE))

    # Seguimiento de plazos (numérico) + multas por problemática
    if seguimiento is not None:
        # "Por multar" se muestra aparte y se descuenta de "Sin multa"
        _con_multa = seguimiento.get('con_multa', 0)
        _por_multar = seguimiento.get('canalizados', 0)
        _sin_multa = max(0, seguimiento.get('sin_multa', 0) - _por_multar)
        _cumpl = seguimiento.get('cumplidos', 0)
        _incum = seguimiento.get('incumplimientos', 0)
        _pend = seguimiento.get('vencidos', 0)
        _revis = _cumpl + _incum
        seg_block = [Paragraph('Seguimiento de plazos', H2)]
        seg_block.append(Paragraph('De las <b>%d</b> amonestaciones revisadas, se muestran dos desgloses del mismo total: por <b>resultado</b> (cumplió / incumplió) y por <b>sanción</b> (multa). "Amonestaciones por verificar" son aparte: las %d que aún faltan revisar.'
                                   % (_revis, _pend), NOTE))
        # Tabla agrupada (grupo con banda oscura, subtítulo con banda clara, ítem con sangría)
        _GRP = colors.HexColor('#3d4a5a'); _SUBC = colors.HexColor('#e8edf1')
        _grpst = ParagraphStyle('grp', parent=Cb, textColor=colors.white)
        _subst = ParagraphStyle('subh', parent=C, fontName='Helvetica-Bold', textColor=DARK)
        seg_body = [[P('Seguimiento', CB), P('Cantidad', CBc)]]
        seg_sty = [('BACKGROUND', (0, 0), (-1, 0), DARK),
                   ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')),
                   ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                   ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]

        def _grp(txt):
            r = len(seg_body); seg_body.append([Paragraph(escape(txt), _grpst), P('', C)])
            seg_sty.extend([('BACKGROUND', (0, r), (-1, r), _GRP), ('SPAN', (0, r), (1, r))])

        def _sub(txt):
            r = len(seg_body); seg_body.append([Paragraph(escape(txt), _subst), P('', C)])
            seg_sty.extend([('BACKGROUND', (0, r), (-1, r), _SUBC), ('SPAN', (0, r), (1, r))])

        def _it(txt, qty):
            seg_body.append([P('   ' + txt, C), P(qty, Cc)])

        _grp('Pendientes por revisar')
        _it('Amonestaciones por verificar', _pend)
        _grp('Amonestaciones revisadas: %d' % _revis)
        _sub('Por resultado')
        _it('Cumplidas', _cumpl)
        _it('Incumplidas', _incum)
        _sub('Por sanción')
        _it('Con multa', _con_multa)
        _it('Por multar', _por_multar)
        _it('Sin multa', _sin_multa)
        seg_t = Table(seg_body, colWidths=[6.2 * cm, 2.4 * cm])
        seg_t.setStyle(TableStyle(seg_sty))
        if multa_prob:
            multas_col = columna('Multas por problemática', multa_prob)
        else:
            multas_col = Paragraph('Sin multas registradas en el periodo.', NOTE)
        seg_row = Table([[seg_t, multas_col]], colWidths=[9.0 * cm, 8.0 * cm])
        seg_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        seg_block.append(seg_row)

        # Gráficas de pay (con %) de las particiones del seguimiento
        def col_fija(titulo, items, hx):
            return Table([[mini(titulo, items, hx)], [Spacer(1, 3)], [_pie(items, hx)]],
                         colWidths=[7.6 * cm], style=[('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'TOP')])
        pays = []
        res_items = [('Cumplidos', seguimiento.get('cumplidos', 0)), ('Incumplimientos', seguimiento.get('incumplimientos', 0))]
        if sum(v for _, v in res_items) > 0:
            pays.append(col_fija('Resultado', res_items, ['#27ae60', '#e74c3c']))
        multa_items = [('Con multa', _con_multa), ('Por multar', _por_multar), ('Sin multa', _sin_multa)]
        if sum(v for _, v in multa_items) > 0:
            pays.append(col_fija('Multa', multa_items, ['#e67e22', '#9b59b6', '#3b82f6']))
        if pays:
            while len(pays) < 3:
                pays.append('')
            pay_row = Table([pays], colWidths=[8.5 * cm, 8.5 * cm, 8.5 * cm])
            pay_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (0, 0), (-1, -1), 'LEFT')]))
            seg_block.append(Spacer(1, 10))
            seg_block.append(pay_row)

        seg_block.append(Paragraph('Nota: un mismo caso puede llevar multa o no y ser canalizado a la dirección correspondiente. Cada multa se cuenta una vez, por su problemática principal (la primera del folio).', NOTE))
        S.append(PageBreak())
        S.extend(seg_block)

    # Avance del operativo (página 2)
    S.append(PageBreak())
    S.append(Paragraph('Avance del operativo', H2))
    pct = ncov / total_poly
    bar = Drawing(300, 24)
    bar.add(Rect(0, 4, 232, 15, rx=4, ry=4, fillColor=LGREY, strokeColor=None))
    bar.add(Rect(0, 4, 232 * pct, 15, rx=4, ry=4, fillColor=colors.HexColor('#27ae60'), strokeColor=None))
    bar.add(String(240, 8, '%d/%d (%d%%)' % (ncov, total_poly, round(pct * 100)), fontName='Helvetica-Bold', fontSize=10, fillColor=DARK))
    tbody = [[P('Equipo', CB), P('Políg.', CBc), P('Asign.', CBc), P('Faltan', CBc), P('Manzanas', CBc)]]
    for k in sorted(asignados):
        ps = [int(x) for x in asignados[k]]; cub = len([p for p in ps if p in cov])
        tmz = sum(mz.get(p, 0) for p in ps); cmz = sum(min(mc.get(p, 0), mz.get(p, 0)) for p in ps)
        tbody.append([P(tname[k]), P(cub, Cc), P(len(ps), Cc), P(len(ps) - cub, Cc), P('%d/%d' % (cmz, tmz), Cc)])
    tbody.append([P('TOTAL', Cb), P(ncov, Ccb), P(total_poly, Ccb), P(total_poly - ncov, Ccb), P('%d/%d' % (cub_mz, tot_mz), Ccb)])
    tav = Table(tbody, colWidths=[2.8 * cm, 1.6 * cm, 1.7 * cm, 1.5 * cm, 2.2 * cm])
    tav.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GREY]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dfe6ec')), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))

    geo = _load_geo()
    mapa = _mapa_drawing(geo, cov, encurso, tcol, 440) if geo and geo.get('polys') else _grid_fallback(allp, poly_team, cov, tcol)

    bar2 = Drawing(300, 24)
    bar2.add(Rect(0, 4, 232, 15, rx=4, ry=4, fillColor=LGREY, strokeColor=None))
    bar2.add(Rect(0, 4, 232 * pct_mz, 15, rx=4, ry=4, fillColor=colors.HexColor('#e67e22'), strokeColor=None))
    bar2.add(String(240, 8, '%d/%d (%d%%)' % (cub_mz, tot_mz, round(pct_mz * 100)), fontName='Helvetica-Bold', fontSize=10, fillColor=DARK))
    _lbl = ParagraphStyle('lbl', parent=NOTE, fontName='Helvetica-Bold', textColor=DARK, fontSize=8.5)
    izq = Table([[Paragraph('Avance por polígonos', _lbl)], [bar],
                 [Paragraph('Avance por manzanas', _lbl)], [bar2], [Spacer(1, 4)], [tav]], colWidths=[11 * cm])
    izq.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    der = Table([[Paragraph('Mapa del operativo — color = completo · claro = en curso · gris = faltan',
        ParagraphStyle('x', parent=NOTE, fontName='Helvetica-Bold', textColor=DARK))], [mapa]], colWidths=[16 * cm])
    der.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    comp = Table([[izq, der]], colWidths=[11 * cm, 16 * cm]); comp.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    S.append(comp)
    if encurso:
        enc = [[P('Polígono', CB), P('Equipo', CBc), P('Manzanas', CBc), P('Faltan', CBc)]]
        for p in sorted(encurso):
            enc.append([P('R%d' % p), P('Equipo ' + poly_team[p], Cc), P('%d/%d' % (mc.get(p, 0), mz.get(p, 0)), Cc), P(mz.get(p, 0) - mc.get(p, 0), Cc)])
        te = Table(enc, colWidths=[2.3 * cm, 3.2 * cm, 2.6 * cm, 2.0 * cm])
        te.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), DARK), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GREY]),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dfe4ea')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        S.append(Spacer(1, 8))
        S.append(Paragraph('Polígonos en curso — manzanas que faltan para completarlos', H2))
        S.append(te)
    doc.build(S)
    buf.seek(0)
    return buf.read()


def _mapa_drawing(geo, cov, encurso, tcol, target_w=430):
    sc = target_w / float(geo['w']); dw = target_w; dh = geo['h'] * sc
    d = Drawing(dw, dh); enc = set(encurso or [])
    for p in geo['polys']:
        r = int(p['r']); base = tcol.get(p['team'], DARK)
        if r in cov:
            fill = base; op = 0.9; tc = colors.white
        elif r in enc:
            fill = base; op = 0.38; tc = DARK
        else:
            fill = colors.HexColor('#e3e7ec'); op = 0.75; tc = colors.HexColor('#8a94a3')
        pts = []
        for (x, y) in p['pts']:
            pts += [x * sc, dh - y * sc]
        d.add(RLPolygon(points=pts, fillColor=fill, strokeColor=colors.white, strokeWidth=0.8, fillOpacity=op))
        cx = sum(pt[0] for pt in p['pts']) / len(p['pts']) * sc
        cy = dh - sum(pt[1] for pt in p['pts']) / len(p['pts']) * sc
        d.add(String(cx, cy - 3, 'R%d' % r, fontName='Helvetica-Bold', fontSize=6.5, fillColor=tc, textAnchor='middle'))
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
