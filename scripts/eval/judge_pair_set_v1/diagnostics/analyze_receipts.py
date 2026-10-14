import json,sys,collections
rs=[json.loads(l) for l in open(sys.argv[1])]
ok=[r for r in rs if not r['error']]
print("first-position wins among valid:", sum(r['winner']==r['presented_ids'][0] for r in ok), "/", len(ok))
for k in "DWB":
    v=[r for r in ok if r['kind']==k]
    print(k, "valid", len(v), "first-pos wins", sum(r['winner']==r['presented_ids'][0] for r in v), "correct", sum(r['winner']==r['expected_best'] for r in v) if k!='B' else '-')
d=collections.defaultdict(dict)
for r in rs: d[r['pair_id']][r['order']]=r
cons=[p for p,o in d.items() if p[0]=='D' and all(not o[x]['error'] and o[x]['winner']==o[x]['expected_best'] for x in ('AB','BA'))]
consw=[p for p,o in d.items() if p[0]=='D' and all(not o[x]['error'] for x in ('AB','BA')) and o['AB']['winner']==o['BA']['winner']!=o['AB']['expected_best']]
print("D consistent correct", len(cons), "consistent wrong", len(consw))
print("errors by kind", collections.Counter(r['kind'] for r in rs if r['error']))
print("error types", collections.Counter(r['error'].split(':')[0] for r in rs if r['error']))
