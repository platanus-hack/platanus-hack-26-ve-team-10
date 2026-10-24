"""Build reports/firecrawl-evals/index.html + data/report-data.json from /workspace/prais-evals.
Every number in the report is computed here from the eval files. Run validate_arms.py first.
"""
import json, os, re, statistics as st, collections as C, hashlib
EV = '/workspace/prais-evals/'
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = HERE + '/data/'
J = lambda p: json.load(open(p))
L = lambda p: [json.loads(l) for l in open(p)]

products = J(EV + 'eval-set.json')['products']
P = {p['id']: p for p in products}
runs = L(EV + 'runs.jsonl')
fcv = J(DATA + 'firecrawl-validated.json')
brv = J(DATA + 'browser-validated.json')
base = J(EV + 'baseline-validated.json')
browser = L(EV + 'baseline-browser.jsonl')
METH = {'A': 'A · Agent', 'B': 'B · Search+scrape', 'C': 'C · Search+escalation', 'D': 'D · Mercado Libre direct'}
CLAUDE = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']

def usd(o):  # identical rule to baseline/summarize.py usd()
    p = o.get('price')
    try:
        if p['currency'] == 'USD': return float(p['amount'])
    except Exception: pass

def med(x): return st.median(x) if x else None
def p90(x):
    if not x: return None
    x = sorted(x); return x[min(len(x) - 1, int(round(0.9 * (len(x) - 1))))]

# ---- final run per (method, product) = latest started_at; earlier ones are pilot/retries
final = {}
for r in runs:
    k = (r['method'], r['product_id'])
    if k not in final or r['started_at'] > final[k]['started_at']: final[k] = r
final_ids = {r['run_id'] for r in final.values()}

# ---- credits cross-check
log = open(EV + 'full.log').read()
log_spent = [(m, int(n)) for m, n in re.findall(r'== after (\w) spent (\d+)', log)]
credits = dict(
    reported_all=sum(r['credits_reported'] or 0 for r in runs),
    reported_final=sum(r['credits_reported'] or 0 for r in runs if r['run_id'] in final_ids),
    used_all_inflated=sum(r['credits_used'] or 0 for r in runs),
    stated_total=2684, stated_balance=[101525, 98841], stated_delta=101525 - 98841,
    full_log_cumulative=log_spent,
    full_log_by_method={m: n - (log_spent[i-1][1] if i else 0) for i, (m, n) in enumerate(log_spent)},
    by_method={m: dict(reported=sum(r['credits_reported'] or 0 for r in runs if r['method'] == m),
                       runs=sum(1 for r in runs if r['method'] == m),
                       agent_steps_null_or_zero=sum(1 for r in runs if r['method'] == m for s in r['steps'] if s['endpoint'] == 'agent' and not s.get('credits')))
               for m in METH},
)
# USD per credit: not in the eval files -> ASSUMPTION from public Firecrawl pricing (accessed 2026-10-24)
USD_PER_CREDIT = dict(standard_plan=99 / 100000, payg_standard=5 / 2000,
    source='https://www.firecrawl.dev/pricing and https://docs.firecrawl.dev/billing (Standard: $99/mo for 100,000 credits; pay-as-you-go $5 per 2,000 credits). ASSUMPTION: the plan of the account used is not recorded in the eval files.')

# ---- offers
fc_off = [x for x in fcv['offers'] if x['run_id'] in final_ids]
def arm_of_fc(x): return 'FC-' + x['method']
offers = []  # unified rows
for x in fc_off:
    o = x['offer']; v = x['validation']
    offers.append(dict(arm='FC-' + x['method'], pid=x['product_id'], run=x['run_id'], o=o, status=v['status'], reason=v.get('reason'), ev=v.get('ve_evidence'), http=v.get('http'), harness_pass=o.get('_ve_pass')))
for r in base:
    if r['model_id'] not in CLAUDE + ['gemini-3-flash-preview']: continue
    for i, o in enumerate(r['offers']):
        if not isinstance(o, dict): continue
        v = o['validation']
        offers.append(dict(arm=r['model_id'], pid=r['product_id'], run=f"{r['model_id']}/{r['product_id']}/{r['prompt_kind']}", o={k: o.get(k) for k in ('title', 'url', 'price', 'merchant', 'product')}, status=v['status'], reason=v.get('reason'), ev=v.get('ve_evidence'), http=v.get('http')))
for x in brv['offers']:
    v = x['validation']; arm = 'ai_overview' if x['surface'] == 'ai_overview' else 'gemini_app'
    offers.append(dict(arm=arm, pid=x['product_id'], run=f"{arm}/{x['product_id']}", o=x['offer'], status=v['status'], reason=v.get('reason'), ev=v.get('ve_evidence'), http=v.get('http')))

ARMS = ['FC-A', 'FC-B', 'FC-C', 'FC-D', 'FC-any'] + CLAUDE + ['ai_overview', 'gemini_app']
def in_arm(o, a): return o['arm'].startswith('FC-') if a == 'FC-any' else (o['arm'] == 'ai-any' and False) or o['arm'] == a
arm_summary = {}
for a in ARMS + ['gemini-3-flash-preview']:
    O = [o for o in offers if in_arm(o, a)]
    c = C.Counter(o['status'] for o in O)
    V = [o for o in O if o['status'] == 'verified']
    arm_summary[a] = dict(claimed=len(O), verified=c['verified'], unverifiable=c['unverifiable'], hallucinated=c['hallucinated'],
                          products_with_verified=len({o['pid'] for o in V}),
                          products_with_verified_usd=len({o['pid'] for o in V if usd(o['o'])}))

# ---- report-level flags (validate.py verdicts are NOT changed; these only gate the price comparisons)
import re
# (1) suspected thousands-separator parse error: amount string looks like "1.921" (1-3 digits, dot, exactly 3 digits)
#     AND the value is < 10% of the median of the product's other verified USD prices (all arms).
PARSE_RE = re.compile(r'^\d{1,3}\.\d{3}$')
for o in offers:
    o['flag'] = None
for pid in P:
    V = [o for o in offers if o['pid'] == pid and o['status'] == 'verified' and usd(o['o'])]
    for o in V:
        amt = str((o['o'].get('price') or {}).get('amount', ''))
        others = [usd(x['o']) for x in V if x is not o]
        if PARSE_RE.match(amt) and others and usd(o['o']) < 0.1 * med(others):
            o['flag'] = 'suspected parse error'
def ok_price(o): return o['status'] == 'verified' and usd(o['o']) and not o['flag']
parse_flagged = [dict(pid=o['pid'], arm=o['arm'], run=o['run'], amount=o['o']['price']['amount'], title=o['o'].get('title'), url=o['o'].get('url')) for o in offers if o['flag']]

# (2) possible variant mismatch between the two lowest offers (FC-any lowest vs best-Claude lowest):
#     price ratio max/min >= 1.25, OR a spec with the same unit appears in both titles with no common value.
VAR_RATIO = 1.25
VAR_MIN_USD = 5.0  # ignore ratio on cheap staples (e.g. $0.94 vs $1.25 flour)
UNIT = {'gb': 'gb', 'kg': 'kg', 'pies': 'pies', 'btu': 'btu', 'w': 'w', 'v': 'v', 'va': 'va', 'kva': 'kva', 'und': 'und', 'unidades': 'und', '"': 'in', '″': 'in', 'pulgadas': 'in'}
SPEC_RE = re.compile(r'(\d+(?:[.,]\d+)*(?:/\d+(?:[.,]\d+)*)*)\s*(gb|kg|pies|btu|kva|va|w|v|und|unidades|pulgadas|"|″)(?![a-z])', re.I)
def specs(t):
    out = {}
    for n, u in SPEC_RE.findall(t or ''):
        u = UNIT[u.lower()]
        for n in n.split('/'):
            n = n.replace(',', '.')
            if u in ('btu', 'und') or re.match(r'^\d{1,3}\.\d{3}$', n): n = n.replace('.', '')
            out.setdefault(u, set()).add(float(n))
    return out
def variant_check(a, b):
    pa, pb = usd(a['o']), usd(b['o']); why = []
    if pa and pb and max(pa, pb) / min(pa, pb) >= VAR_RATIO and abs(pa - pb) >= VAR_MIN_USD: why.append(f'price ratio {max(pa, pb) / min(pa, pb):.2f} >= {VAR_RATIO}')
    sa, sb = specs(a['o'].get('title')), specs(b['o'].get('title'))
    for u in sa.keys() & sb.keys():
        if not (sa[u] & sb[u]): why.append(f'spec "{u}" differs: {sorted(sa[u])} vs {sorted(sb[u])}')
    return why

# ---- per-product lowest verified USD per arm, and savings vs AI (parse-error offers excluded)
per_product = {}
for pid in P:
    row = {}; low = {}
    for a in ARMS:
        VO = [o for o in offers if in_arm(o, a) and o['pid'] == pid and ok_price(o)]
        V = [usd(o['o']) for o in VO]
        n = sum(1 for o in offers if in_arm(o, a) and o['pid'] == pid and o['status'] == 'verified')
        row[a] = dict(min_usd=min(V) if V else None, median_usd=med(V), n_verified=n)
        low[a] = min(VO, key=lambda o: usd(o['o'])) if VO else None
    ai = [low[m] for m in CLAUDE if low[m]]
    ai_low = min(ai, key=lambda o: usd(o['o'])) if ai else None
    row['ai_best_min_usd'] = usd(ai_low['o']) if ai_low else None
    f = row['FC-any']['min_usd']
    row['saving_vs_ai_best'] = (row['ai_best_min_usd'] - f) if (f is not None and ai_low) else None
    for m in CLAUDE:
        row['saving_vs_' + m] = (row[m]['min_usd'] - f) if (f is not None and row[m]['min_usd'] is not None) else None
    fl = low['FC-any']
    row['fc_low'] = dict(arm=fl['arm'], title=fl['o'].get('title'), url=fl['o'].get('url')) if fl else None
    row['ai_low'] = dict(arm=ai_low['arm'], title=ai_low['o'].get('title'), url=ai_low['o'].get('url')) if ai_low else None
    row['variant_flag'] = variant_check(fl, ai_low) if (fl and ai_low) else []
    row['parse_flagged'] = [x for x in parse_flagged if x['pid'] == pid]
    per_product[pid] = row
both = [pid for pid, r in per_product.items() if r['saving_vs_ai_best'] is not None]
clean = [p for p in both if not per_product[p]['variant_flag']]
headline = dict(
    products=len(P),
    fc_verified=arm_summary['FC-any']['verified'],
    ai_verified={m: arm_summary[m]['verified'] for m in CLAUDE},
    products_with_both=len(both),
    variant_flagged=[p for p in both if per_product[p]['variant_flag']],
    products_compared=len(clean),
    fc_cheaper=sum(1 for p in clean if per_product[p]['saving_vs_ai_best'] > 0),
    equal=sum(1 for p in clean if per_product[p]['saving_vs_ai_best'] == 0),
    ai_cheaper=sum(1 for p in clean if per_product[p]['saving_vs_ai_best'] < 0),
    median_saving_usd=med([per_product[p]['saving_vs_ai_best'] for p in clean]),
    median_saving_usd_incl_variant_flagged=med([per_product[p]['saving_vs_ai_best'] for p in both]),
    fc_only_products=[p for p, r in per_product.items() if r['FC-any']['min_usd'] is not None and r['ai_best_min_usd'] is None],
    ai_only_products=[p for p, r in per_product.items() if r['FC-any']['min_usd'] is None and r['ai_best_min_usd'] is not None],
    parse_flagged=parse_flagged,
    rules=dict(parse_error='amount string matches ^\\d{1,3}\\.\\d{3}$ and value < 10% of median of the product\'s other verified USD prices',
               variant=f'FC lowest vs best-Claude lowest: price ratio >= {VAR_RATIO} and gap >= ${VAR_MIN_USD:.0f}, or same-unit spec in both titles with no common value'),
)
for a in ARMS + ['gemini-3-flash-preview']:
    arm_summary[a]['products_with_verified_usd'] = len({o['pid'] for o in offers if in_arm(o, a) and ok_price(o)})

# ---- time and cost
timing = {}
for m in METH:
    R = [final[(m, p)] for p in P if (m, p) in final]
    tf = [r['t_first_valid_ve_ms'] / 1000 for r in R if r['t_first_valid_ve_ms'] is not None]
    tt = [r['t_total_ms'] / 1000 for r in R]
    cr = [r['credits_reported'] or 0 for r in R]
    timing['FC-' + m] = dict(runs=len(R), with_first_valid=len(tf), first_valid_median_s=med(tf), first_valid_p90_s=p90(tf), total_median_s=med(tt), total_p90_s=p90(tt),
                            credits_reported_sum=sum(cr), credits_balance_delta_full_log=credits['full_log_by_method'].get(m), credits_per_query_median=med(cr), credits_per_query_mean=sum(cr) / len(cr) if cr else None,
                            usd_per_query_mean_standard=(sum(cr) / len(cr)) * USD_PER_CREDIT['standard_plan'] if cr else None,
                            usd_per_query_mean_payg=(sum(cr) / len(cr)) * USD_PER_CREDIT['payg_standard'] if cr else None,
                            note='t_first_valid uses the harness VE check at run time (harness.py), not validate.py')
for mdl in CLAUDE + ['gemini-3-flash-preview']:
    R = [r for r in base if r['model_id'] == mdl]
    lat = [r['latency_s'] for r in R if r['latency_s']]
    tfv = [r['latency_s'] for r in R if r['latency_s'] and any(isinstance(o, dict) and o['validation']['status'] == 'verified' for o in r['offers'])]
    cost = [(r['cost_usd'] or 0) + (r['extract_cost_usd'] or 0) for r in R]
    timing[mdl] = dict(runs=len(R), with_first_valid=len(tfv), first_valid_median_s=med(tfv), first_valid_p90_s=p90(tfv), total_median_s=med(lat), total_p90_s=p90(lat),
                       usd_sum=sum(cost), usd_per_query_mean=sum(cost) / len(cost), note='single answer: time to first valid = full latency of calls that produced >=1 verified offer; cost is Claude Code reported equivalent (subscription)')
gapp = [r for r in browser if r['surface'] == 'gemini_app']
timing['gemini_app'] = dict(runs=len(gapp), total_median_s=med([r['seconds'] for r in gapp if r['seconds']]), note='PARTIAL: only p01')
aio = [r for r in browser if r['surface'] == 'ai_overview']
browser_summary = dict(ai_overview_rows=len(aio), ai_overview_shown=sum(1 for r in aio if r.get('model_label')), gemini_app_rows=len(gapp),
                       gemini_app_products=[r['product_id'] for r in gapp])

# ---- link inventory
links = []
for r in runs:
    for s in r['steps']:
        links.append(dict(run_id=r['run_id'], final=r['run_id'] in final_ids, method=r['method'], pid=r['product_id'], endpoint=s['endpoint'], job_id=s['job_id'], url=s['url'], http=s['http'], credits=s['credits'], latency_ms=s['latency_ms'], note=s.get('note')))
run_rows = [dict(run_id=r['run_id'], final=r['run_id'] in final_ids, method=r['method'], pid=r['product_id'], raw='/workspace/prais-evals/' + r['raw_json_path'],
                 credits_reported=r['credits_reported'], t_first_s=(r['t_first_valid_ve_ms'] / 1000 if r['t_first_valid_ve_ms'] is not None else None), t_total_s=r['t_total_ms'] / 1000,
                 n_results=r['n_results'], n_harness_ve=r['n_ve_pass'],
                 n_validated=sum(1 for x in fcv['offers'] if x['run_id'] == r['run_id'] and x['validation']['status'] == 'verified'),
                 errors=sorted(set(e[:120] for e in r['errors'])), escalations=r.get('escalations')) for r in runs]
ai_rows = [dict(model=r['model_id'], pid=r['product_id'], kind=r['prompt_kind'], latency_s=r['latency_s'], cost=(r['cost_usd'] or 0) + (r['extract_cost_usd'] or 0), n=len([o for o in r['offers'] if isinstance(o, dict)]),
                verified=sum(1 for o in r['offers'] if isinstance(o, dict) and o['validation']['status'] == 'verified'), error=r.get('error')) for r in base]
br_rows = [dict(pid=r['product_id'], surface=r['surface'], label=r.get('model_label'), url=r.get('chat_url') or r.get('search_url'), share=r.get('share_url'), seconds=r.get('seconds'), n_sources=len(r.get('source_urls') or [])) for r in browser]
link_check = json.load(open(DATA + 'link-check.json')) if os.path.exists(DATA + 'link-check.json') else None

# ---- prompts / params
agent_step = next(s for r in runs if r['method'] == 'A' for s in r['steps'] if s['endpoint'] == 'agent' and s['http'] == 200)
scrape_step = next(s for r in runs if r['method'] == 'B' for s in r['steps'] if s['endpoint'] == 'scrape')
search_step = next(s for r in runs if r['method'] == 'B' for s in r['steps'] if s['endpoint'] == 'search')
esc_steps = [s for r in runs if r['method'] == 'C' for s in r['steps'] if s['endpoint'] in ('interact', 'crawl')][:3]
ai_prompts = {k: next(r['prompt'] for r in base if r['model_id'] == 'claude-opus-5-5' and r['prompt_kind'] == k and r['product_id'] == 'p01') for k in ('plain', 'struct')}
prompts = dict(prompts_md=open(EV + 'prompts.md').read(), methods_md=open(EV + 'methods.md').read(), agent_params=agent_step['params'], scrape_params=scrape_step['params'],
               search_params=search_step['params'], escalation_params=esc_steps, ai_prompts_p01=ai_prompts,
               ai_access={m: next(r.get('access') for r in base if r['model_id'] == m) for m in CLAUDE + ['gemini-3-flash-preview']},
               browser_prompt_p01=browser[0]['prompt'], extract_prompt_note='scrape params reference "extract_prompt"; full text is in prompts.md / harness.py')

# daka
daka = [dict(run=r['run_id'], n_results=r['n_results'], n_harness_ve=r['n_ve_pass'], n_validated=sum(1 for x in fcv['offers'] if x['run_id'] == r['run_id'] and x['validation']['status'] == 'verified'),
             statuses=dict(C.Counter(x['validation']['status'] for x in fcv['offers'] if x['run_id'] == r['run_id'])),
             reasons=dict(C.Counter(x['validation'].get('reason') or 'verified' for x in fcv['offers'] if x['run_id'] == r['run_id']))) for r in runs if r['product_id'] == 'p06' and r['run_id'] in final_ids]

# drill-down offers (compact)
drill = []
for o in offers:
    oo = o['o']; m = oo.get('merchant') or {}; pr = oo.get('product') or {}
    drill.append(dict(flag=o['flag'], arm=o['arm'], pid=o['pid'], run=o['run'], status=o['status'], reason=o['reason'], ev=o['ev'], title=oo.get('title'), url=oo.get('url'), price=oo.get('price'), usd=usd(oo),
                      seller=m.get('name'), phone=m.get('phone'), whatsapp=m.get('whatsapp'), instagram=m.get('instagram'), zone=m.get('zone') or m.get('city'), address=m.get('address'),
                      brand=pr.get('brand'), model=pr.get('model'), variant=pr.get('variant'), condition=pr.get('condition'), source_type=(oo.get('source') or {}).get('source_type')))

out = dict(generated_from=EV, validator=fcv['meta'], products=products, methods=METH, arms=ARMS, arm_summary=arm_summary, per_product=per_product, headline=headline,
           credits=credits, usd_per_credit=USD_PER_CREDIT, timing=timing, browser_summary=browser_summary, runs=run_rows, steps=links, ai_runs=ai_rows, browser_runs=br_rows,
           link_check=link_check, prompts=prompts, daka=daka, offers=drill, n_pilot_runs=len(runs) - len(final_ids))
json.dump(out, open(DATA + 'report-data.json', 'w'), ensure_ascii=False, indent=1)
tpl = open(HERE + '/template.html').read()
open(HERE + '/index.html', 'w').write(tpl.replace('/*__DATA__*/null', json.dumps(out, ensure_ascii=False).replace('</', '<\\/')))
print(json.dumps(dict(headline=headline, arm_summary=arm_summary, credits={k: v for k, v in credits.items()}, timing=timing, daka=daka, browser=browser_summary, pilot=len(runs) - len(final_ids)), indent=1, default=str))
