import json, urllib.request

TESTS = [('20000101', (35, 34)), ('20000101', (28, 25)),
         ('20000102', (35, 34)), ('20000102', (28, 25)),
         ('19991127', (51, 48)), ('19991128', (51, 48))]
VARIANTS = {
    'g80': 'groups=80',
    'g81': 'groups=81',
    'nogroup': '',
    'g80+postseason': 'groups=80&seasontype=3',
    'nogroup+postseason': 'seasontype=3',
}
BASE = ('https://site.api.espn.com/apis/site/v2/sports/football/'
        'college-football/scoreboard?limit=400&dates={d}&{extra}')


def get(d, extra):
    req = urllib.request.Request(BASE.format(d=d, extra=extra),
                                 headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def scores(data):
    out = []
    for ev in data.get('events', []):
        try:
            c = ev['competitions'][0]['competitors']
            out.append((ev.get('shortName', '?'),
                        {int(x['score']) for x in c}))
        except Exception:
            pass
    return out


for d, pair in TESTS:
    print(f'\n{d} looking for scores {pair}')
    for name, extra in VARIANTS.items():
        try:
            ev = scores(get(d, extra))
        except Exception as e:
            print(f'  {name:20s} ERROR {e}')
            continue
        hits = [n for n, s in ev if s == set(pair)]
        print(f'  {name:20s} {len(ev):3d} events   found: {hits}')