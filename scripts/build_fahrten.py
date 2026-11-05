#!/usr/bin/env python3
"""Baut fahrplan/zusatz-strecken.json aus der Xunta-GTFS-Datei (xunta.zip).
Aufruf: build_fahrten.py <xunta.zip> <ausgabe.json>
Strecken: F=Fisterra, S=Santiago, C=A Coruña, M=Muxía. Betreiber: Linien XG848* = Arriva, sonst Monbus."""
import csv, io, json, sys, zipfile, datetime, collections

zpath, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zpath)
def rows(name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))

today = datetime.date.today().strftime('%Y%m%d')
names = {r['stop_id']: r['stop_name'] for r in rows('stops.txt')}
G = {'F': {k for k, v in names.items() if v == 'Fisterra'},
     'M': {k for k, v in names.items() if v in ('Muxía', 'Muxía (porto)')},
     'S': {k for k, v in names.items() if v.upper().startswith('SANTIAGO E.I')},
     'C': {k for k, v in names.items() if 'Coruña E.' in v}}
route = {r['route_id']: r['route_short_name'] for r in rows('routes.txt')}
cal = {r['service_id']: r for r in rows('calendar.txt')}
trips = {r['trip_id']: (r['service_id'], route[r['route_id']]) for r in rows('trips.txt')
         if r['service_id'] in cal and cal[r['service_id']]['end_date'] >= today}
tm = collections.defaultdict(dict)
with z.open('stop_times.txt') as f:
    rd = csv.reader(io.TextIOWrapper(f, encoding='utf-8-sig'))
    h = next(rd)
    ti, di, ai, si, qi = [h.index(x) for x in ('trip_id', 'departure_time', 'arrival_time', 'stop_id', 'stop_sequence')]
    for r in rd:
        t = r[ti]
        if t not in trips: continue
        for g, ids in G.items():
            if r[si] in ids and g not in tm[t]:
                tm[t][g] = (int(r[qi]), r[ai][:5], r[di][:5])

days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
def norm(t):  # GTFS erlaubt 24:xx
    h, m = t.split(':'); return f'{int(h) % 24}:{m}'
def build(a, b):
    res = collections.defaultdict(set)
    for t, x in tm.items():
        if a in x and b in x and x[a][0] < x[b][0]:
            sv, rn = trips[t]; c = cal[sv]
            op = 'Arriva' if rn.startswith('XG848') else 'Monbus'
            key = (norm(x[a][2]), norm(x[b][1]), op)
            for i, d in enumerate(days):
                if c[d] == '1': res[key].add(i)
    g = {'mo-fr': [], 'sa': [], 'so': []}
    for k in sorted(res, key=lambda k: (int(k[0].split(':')[0]) * 60 + int(k[0].split(':')[1]), k[1], k[2])):
        ds = res[k]; s = f'{k[0]}-{k[1]}|{k[2]}'
        if ds & {0, 1, 2, 3, 4}: g['mo-fr'].append(s)
        if 5 in ds: g['sa'].append(s)
        if 6 in ds: g['so'].append(s)
    return g

strecken = {a + b: build(a, b) for a, b in
            ['FS', 'SF', 'FC', 'CF', 'FM', 'MF', 'MS', 'SM', 'MC', 'CM']}
if not all(any(v) for v in strecken.values()):
    sys.exit('FEHLER: eine Strecke ist leer – Datei wird nicht geschrieben: ' + str([k for k, v in strecken.items() if not any(v.values())]))
fmt = lambda d: f'{d[:4]}-{d[4:6]}-{d[6:]}' if d else ''
gb = fmt(max(cal[trips[t][0]]['end_date'] for t, x in tm.items() if len(x) > 1))
try:
    alt = json.load(open(out, encoding='utf-8'))
    if alt.get('strecken') == strecken and alt.get('gueltig_bis') == gb:
        print('unverändert – nichts geschrieben'); sys.exit(0)
except (OSError, ValueError):
    pass
json.dump({'stand': datetime.date.today().isoformat(), 'gueltig_bis': gb,
           'quelle': 'NAP Xunta de Galicia (Transporte Público de Galicia)', 'strecken': strecken},
          open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('geschrieben:', out, {k: sum(len(v) for v in s.values()) for k, s in strecken.items()})
