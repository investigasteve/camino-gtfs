#!/usr/bin/env python3
"""Baut das Fahrplan-Folleto: HTML (A4 quer, 2 Blätter beidseitig = 8 A5-Seiten), optional PDF via Chrome.
Aufruf: build_folleto.py [--pdf]  (PDF braucht: pip install playwright; playwright install chromium)   Daten: fahrplan/*.json, Bilder: fahrplan/assets"""
import base64, html, json, os, subprocess, sys, datetime
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fahrplan')
J = lambda n: json.load(open(os.path.join(D, n), encoding='utf-8'))
zj, preise, tu = J('zusatz-strecken.json'), J('preise.json'), J('tussa-6a.json')
img = lambda n: 'data:image/png;base64,' + base64.b64encode(open(os.path.join(D, 'assets', n), 'rb').read()).decode()
namen = {'F': 'FISTERRA', 'S': 'SANTIAGO', 'C': 'A CORUÑA', 'M': 'MUXIA'}
dt = lambda d: datetime.date.fromisoformat(d).strftime('%d.%m.%Y') if d else '-'
HINWEIS = ['*La responsabilidad de posibles cambios de horarios es de las líneas de autobuses*',
           f"Actualizado: {dt(zj['stand'])}  ·  válido hasta: {dt(zj['gueltig_bis'])}",
           'Fuente: NAP – Ministerio de Transportes, Xunta de Galicia', '(A) = Arriva - (M) = Monbus']
hint = lambda lines=HINWEIS: '<div class="hint">' + '<br>'.join(html.escape(x) for x in lines) + '</div>'
tm = lambda t: t.lstrip('0') or '0'

def tabelle(code):
    g = zj['strecken'][code]
    cols = [sorted(g[k], key=lambda f: (int(f.split(':')[0]), int(f.split(':')[1].split('-')[0]))) for k in ('mo-fr', 'sa', 'so')]
    n = max(len(c) for c in cols)
    h = f'<h2>{namen[code[0]]} - {namen[code[1]]} {preise.get(code, "")}</h2><table class="t"><tr><th class="y" colspan=2>Lunes - Viernes</th><th class="b" colspan=2>Sábado</th><th class="p" colspan=2>Domingo | Festivo</th></tr><tr class="s"><td>Salida</td><td>Llegada</td><td>Salida</td><td>Llegada</td><td>Salida</td><td>Llegada</td></tr>'
    for i in range(n):
        h += '<tr>'
        for c in cols:
            if i < len(c):
                tt, op = c[i].split('|'); a, b = tt.split('-')
                h += f'<td>{tm(a)} ({op[0]})</td><td>{tm(b)}</td>'
            else: h += '<td></td><td></td>'
        h += '</tr>'
    return h + '</table>'

def busart(a):
    h = int(a.split(':')[0]); return 'Bus nocturno' if h >= 23 or h < 6 else ('Bus tardío' if h >= 21 else 'Bus diurno')
def tussa(key):
    hs = key == 'hs'
    titel = 'SANTIAGO - AEROPUERTO (TUSSA 6A) 1,00€' if hs else 'AEROPUERTO - SANTIAGO (TUSSA 6A) 1,00€'
    head = (['Hórreo (Est. Intermodal) Salida', 'San Lázaro (solo subida)', 'San Marcos (solo subida)', 'Aeropuerto Llegada aprox.'] if hs else
            ['Aeropuerto Salida', 'San Marcos (solo bajada)', 'San Lázaro (solo bajada)', 'Hórreo (Est. Intermodal) Llegada aprox.']) + ['Servicio', 'Tipo de bus']
    h = f'<h2>{titel}</h2><table class="t tu"><tr>' + ''.join(f'<th class="{c}">{x}</th>' for x, c in zip(head, 'yybbpp')) + '</tr>'
    for z in tu[key]:
        d = z[0] == 'D'
        h += f'<tr><td>{z[1]}</td><td>{"" if d else z[3]}</td><td>{"" if d else z[4]}</td><td>{z[2]}</td><td>{"Directo" if d else "con paradas"}</td><td>{busart(z[1])}</td></tr>'
    return h + '</table>'

TU_HINT = ['*Todos los días · Horas de llegada aproximadas*', '*Bus diurno hasta las 20:59 · bus tardío de 21:00 a 22:59 · bus nocturno desde las 23:00 (hora de salida)*',
           'Vigente desde el 28.05.2026', 'Fuente: Tussa – Transporte urbano de Santiago de Compostela, línea 6A']
page = lambda inner, cls='': f'<div class="page {cls}">{inner}</div>'
flyer = f'''<div class="fl"><div class="top"><div><div class="h1">Tu Camino<br>en el móvil.</div><p class="sub">Tu mapa del Camino, gratis y sin registro.</p>
<p><b>Cerca de mí:</b> farmacia, médico, cajero y autobús</p><p><b>Sellos digitales</b> de cada lugar del Camino</p><p><b>Avisos</b> de tiempo e incendios</p><p><b>Noticias</b> y horarios de misa en cada lugar</p></div>
<img class="logo" src="{img('logo.png')}"></div>
<div class="mid"><img class="qr" src="{img('qr.png')}"><div class="esc"><div class="h2">Escanea.</div><p>Apunta la cámara al código,<br>toca el enlace y listo.</p><p class="url">app.steffenpfeiffer.es</p></div></div>
<p class="langs">ES · EN · DE · GL · FR · sin tienda de aplicaciones<br><b>Editorial Investigasteve · Fisterra</b></p><div class="ml">
<div><b class="l">DEUTSCH</b><h3>Dein Camino im Handy.</h3><p>Karte mit „In meiner Nähe“ (Apotheke, Arzt, Geldautomat, Bus), digitale Pilgerstempel, Wetter- und Brandwarnungen, Neuigkeiten und Messzeiten. Scannen, Link antippen, fertig.</p></div>
<div><b class="l">GALEGO</b><h3>O teu Camiño no peto.</h3><p>Mapa con «Preto de min» (farmacia, médico, caixeiro, autobús), selos dixitais de peregrino, avisos de tempo e de incendios, novas e horarios de misa. Escanea, toca a ligazón e listo.</p></div>
<div><b class="l">ENGLISH</b><h3>Your Camino in your pocket.</h3><p>Map with “Near me” (pharmacy, doctor, ATM, bus), digital pilgrim stamps, weather and fire warnings, news and Mass times. Scan, tap the link, done.</p></div>
<div><b class="l">FRANÇAIS</b><h3>Votre Chemin dans la poche.</h3><p>Carte avec « Près de moi » (pharmacie, médecin, distributeur, bus), tampons de pèlerin numériques, alertes météo et incendies, actualités et horaires des messes. Scannez, touchez le lien, c'est prêt.</p></div></div>
<div class="foot"><img src="{img('qr.png')}"><div><b>app.steffenpfeiffer.es</b><br>Editorial Investigasteve · Steffen Pfeiffer · Fisterra<br><small>Digitale Stempel · sellos digitales · digital stamps: complemento voluntario, no sustituyen a la credencial oficial.</small></div></div></div>'''
P = {1: page(tabelle('FS') + tabelle('SF') + hint()), 2: page(tabelle('FC') + tabelle('CF') + hint()),
     3: page(tabelle('MF') + tabelle('FM') + hint()), 4: page(tabelle('MS') + tabelle('SM') + hint()),
     5: page(tabelle('MC') + tabelle('CM') + hint()), 6: page(tussa('hs') + hint(TU_HINT), 'tu'),
     7: page(tussa('sh') + hint(TU_HINT), 'tu'), 8: page(flyer)}
sheets = [(8, 1), (2, 7), (6, 3), (4, 5)]
css = '''@page{size:A4 landscape;margin:0}*{box-sizing:border-box}body{margin:0;font-family:"Liberation Sans",Arial,sans-serif;color:#000}
.sheet{width:297mm;height:210mm;display:flex;page-break-after:always;overflow:hidden}.page{width:148.5mm;height:210mm;padding:8mm 7mm;position:relative}
h2{font-size:11.5pt;margin:3mm 0 1.2mm}.t{width:100%;border-collapse:collapse;font-size:9.5pt;border:1px solid #000;text-align:center}
.t td,.t th{padding:1.6mm 0.5mm;border-left:1px solid #000}.t th{font-size:8pt;border-bottom:1px solid #000}.s td{font-size:7.5pt;font-style:italic;padding:.5mm}
.y{background:#ffffc7}.b{background:#bdd7ee}.p{background:#ffb3d1}.t tr:nth-child(2n+3) td{background:#e7e7e7}
.hint{position:absolute;left:7mm;right:7mm;bottom:7mm;text-align:center;color:#d00;font-size:7pt;line-height:1.5}
.tu h2{margin-top:0}.tu .t{font-size:6.1pt;table-layout:fixed}.tu .t td{padding:.2mm .2mm;white-space:nowrap;line-height:1.12}.tu .t th{font-size:5.4pt;padding:.6mm .2mm;line-height:1.1}.tu .hint{font-size:6.2pt;line-height:1.35}
.fl .h1{font-size:30pt;font-weight:bold;line-height:1.05}.fl .top{display:flex;justify-content:space-between;gap:4mm}.fl .logo{width:38mm;height:38mm}
.fl p{margin:1.2mm 0;font-size:8.5pt}.fl .sub{font-size:9.5pt;margin-top:3mm}.fl .mid{display:flex;gap:6mm;margin-top:5mm;align-items:center}.fl .qr{width:62mm;height:62mm}
.fl .h2{font-size:20pt;font-weight:bold}.fl .url{font-weight:bold}.fl .langs{font-size:7.5pt;border-top:1px solid #000;margin-top:3mm;padding-top:2mm}
.fl .ml{display:grid;grid-template-columns:1fr 1fr;gap:3mm 5mm;border-top:1px solid #999;margin-top:3mm;padding-top:3mm}.fl .l{font-size:6pt;letter-spacing:.1em}
.fl h3{margin:0;font-size:9.5pt}.fl .ml p{font-size:6.8pt;margin:.5mm 0}.fl .foot{display:flex;gap:4mm;align-items:center;margin-top:4mm;font-size:8pt}.fl .foot img{width:20mm;height:20mm}
.fl small{font-size:6.3pt}'''
out = '<!doctype html><meta charset="utf-8"><style>' + css + '</style>' + ''.join(f'<div class="sheet">{P[a]}{P[b]}</div>' for a, b in sheets)
hp = os.path.join(D, 'Busfahrplan-Folleto.html'); open(hp, 'w', encoding='utf-8').write(out)
if '--pdf' in sys.argv:
    from playwright.sync_api import sync_playwright
    pdf = os.path.join(D, 'Busfahrplan-Folleto.pdf')
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto('file://' + os.path.abspath(hp))
        pg.pdf(path=pdf, prefer_css_page_size=True, print_background=True); b.close()
    os.remove(hp); print('PDF:', pdf)
else: print('HTML:', hp)
