"""Apply the UNMODIFIED baseline/validate.py check() to Firecrawl offers and browser rows.

validate.py runs at import and has no CLI, so we exec its source up to (not including)
the line starting with 'allo=' (the part that loops over baseline.jsonl and writes
baseline-validated.json). Every function used (fetch, ve, price_on, prod_on, check) is
byte-identical to validate.py; nothing is loosened. sha256 of validate.py is recorded.
Run with cwd = a scratch dir (validate.py caches fetched pages in ./pages).
"""
import json, glob, os, sys, hashlib, concurrent.futures as cf
EV = '/workspace/prais-evals/'
OUT = os.path.dirname(os.path.abspath(__file__)) + '/data/'
os.makedirs(OUT, exist_ok=True)
src = open(EV + 'baseline/validate.py').read()
head = src[:src.index('\nallo=')]
ns = {}
exec(compile(head, EV + 'baseline/validate.py', 'exec'), ns)
check = ns['check']
meta = dict(validator=EV + 'baseline/validate.py', sha256=hashlib.sha256(src.encode()).hexdigest())

# Firecrawl: every offer in every raw run file referenced by runs.jsonl
runs = [json.loads(l) for l in open(EV + 'runs.jsonl')]
fc = []
for r in runs:
    d = json.load(open(EV + r['raw_json_path']))
    for i, o in enumerate(d.get('offers', [])):
        fc.append(dict(run_id=r['run_id'], method=r['method'], product_id=r['product_id'], idx=i, offer=o))
# Browser rows: no structured per-URL price is captured, so each cited source URL becomes an
# offer with title=prompt and price=None (validate.py will mark it unverifiable: no price claimed).
br = [json.loads(l) for l in open(EV + 'baseline-browser.jsonl')]
bo = []
for k, r in enumerate(br):
    su = r.get('source_urls') or []
    if isinstance(su, str): su = [su]
    for u in su:
        bo.append(dict(row=k, product_id=r['product_id'], surface=r['surface'],
                       offer=dict(title=r['prompt'], url=u, price=None)))
with cf.ThreadPoolExecutor(16) as ex:
    res = list(ex.map(lambda x: check(x['offer']), fc + bo))
for x, v in zip(fc + bo, res): x['validation'] = v
json.dump(dict(meta=meta, offers=fc), open(OUT + 'firecrawl-validated.json', 'w'), ensure_ascii=False, indent=1)
json.dump(dict(meta=meta, note='browser rows have no structured price per URL; source_urls checked with price=None', offers=bo),
          open(OUT + 'browser-validated.json', 'w'), ensure_ascii=False, indent=1)
from collections import Counter
print('firecrawl', len(fc), Counter(x['validation']['status'] for x in fc))
print('browser', len(bo), Counter(x['validation']['status'] for x in bo))
