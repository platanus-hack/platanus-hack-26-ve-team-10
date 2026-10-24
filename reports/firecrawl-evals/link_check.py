"""curl every Firecrawl agent link (unauthenticated) and the Gemini chat URL; record HTTP status."""
import json, subprocess, os
EV = '/workspace/prais-evals/'
runs = [json.loads(l) for l in open(EV + 'runs.jsonl')]
br = [json.loads(l) for l in open(EV + 'baseline-browser.jsonl')]
urls = sorted({s['url'] for r in runs for s in r['steps'] if s.get('url')} | {r['chat_url'] for r in br if r.get('chat_url')})
res = {}
for u in urls:
    o = subprocess.run(['curl', '-s', '-L', '-o', '/dev/null', '--max-time', '20', '-w', '%{http_code} %{url_effective}', u], capture_output=True, text=True)
    c, eff = (o.stdout.split(' ', 1) + [''])[:2]
    res[u] = dict(http=int(c or 0), final=eff)
json.dump(dict(method='curl -sL, no login, ' + __import__('time').strftime('%Y-%m-%d %H:%M %z'), results=res), open(os.path.dirname(os.path.abspath(__file__)) + '/data/link-check.json', 'w'), indent=1)
from collections import Counter; print(len(res), Counter(v['http'] for v in res.values()))
