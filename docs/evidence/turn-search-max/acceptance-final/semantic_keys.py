"""Verify the advertised semantic keys from the public comparator contract."""
from run import *
from consume_small import endpoint

def freeze(value):
    if isinstance(value, dict):
        return [[key, freeze(value[key])] for key in sorted(value)]
    if isinstance(value, (list, tuple)):
        return [freeze(item) for item in value]
    return value

def hash_json(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()

observations=[]
cases=read(ROOT/'docs/evidence/turn-search-compare/independent-small-cases.v1.json')
for idx,case in enumerate(cases):
    result=read(OUT/f'small-delivered/case-{idx:03d}/native/trial-1/result.json')
    matches=[]; candidate_hashes=[]
    for node in result['debug_nodes']:
        board_data,values,hand=endpoint(node['state'],result['record']['cards'])
        winner,boards=json.loads(board_data)
        key={'winner':winner,'boards':[[hash_json(freeze(pair)) for pair in board] for board in boards],
             'values':list(values),'hand':sorted(hash_json(freeze(json.loads(card))) for card in hand)}
        matches.append(key==node['semantic_key'])
        if node['candidate']:
            candidate_hashes.append(bytes.fromhex(hash_json(key)))
    candidate_hashes.sort()
    independent_digest=hashlib.sha256(b''.join(candidate_hashes)).hexdigest()
    observations.append({'case':case['id'],'debug_nodes':len(matches),'all_advertised_keys_match':all(matches),
        'candidate_digest_independently_recomputed_from_all_debug_candidate_states':independent_digest,
        'reported_digest_matches':independent_digest==result['candidate_semantic_sha256']})
save(HERE/'semantic-keys-normalized-record.json',observations)
print(json.dumps(observations))
