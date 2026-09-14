"""AIのHTTP入口、保存再生、評価集計の検査。"""
from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
from typing import Any, Iterator

import pytest

from svdeck.battle import Battle, replay
from svdeck.battle_server import create_server
from svdeck.battle_training import summarize
from svdeck.battle_ai import MODEL_PATH, load_weights, model_hash


@pytest.fixture
def server_url() -> Iterator[str]:
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join()


def post(url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(url+path, json.dumps(body).encode(), {'Content-Type':'application/json'})
    with urllib.request.urlopen(request) as response:
        result: dict[str, Any] = json.load(response)
    return result


def test_ai_step_keeps_decision_through_replay_and_branch(server_url: str) -> None:
    battle = Battle({'players':[{'board':[{'id':'a','card_id':'test-body'}],'deck':['test-body']*3},
                               {'health':2,'deck':['test-body']*3}]})
    result = post(server_url,'/api/ai-step',{'record':battle.export(),'cursor':0,'policy':'search'})
    assert result['state']['winner']==0
    assert result['decision']['proven_win']
    assert result['record']['frames'][0]['decision']==result['decision']
    restored = post(server_url,'/api/replay',{'record':result['record'],'cursor':1})
    assert restored['record']['frames'][0]['decision']==result['decision']
    assert replay(restored['record']).state == result['state']
    branch = post(server_url,'/api/step',{'record':result['record'],'cursor':0,'action':{'type':'end_turn'}})
    assert 'decision' not in branch['record']['frames'][0]
    assert len(branch['record']['actions'])==1


@pytest.mark.parametrize('policy',['bogus',None,[]])
def test_bad_policy_is_rejected(server_url: str, policy: Any) -> None:
    with pytest.raises(urllib.error.HTTPError) as raised:
        post(server_url,'/api/ai-step',{'record':Battle({}).export(),'policy':policy})
    assert raised.value.code==400


def test_unfinished_games_do_not_become_draws_or_wins() -> None:
    rows = [{'seed':1,'decks':['ramp-dragon','last-words-nightmare'],'seat':i%2,'result':kind,'mean_decision_ms':1}
            for i,kind in enumerate(['win','loss','draw','unfinished'])]
    summary = summarize(rows)
    assert summary['games']==4
    assert [summary[k] for k in ('win','loss','draw','unfinished')]==[1,1,1,1]
    assert summary['score_rate']==.375


def test_shipped_model_matches_evaluated_weights() -> None:
    # AI_NOTE: 評価メモの追記で実行重みと保存評価の識別が切れないことを検査する。
    expected = model_hash(load_weights())
    model = json.loads(MODEL_PATH.read_text())
    assert model['model_hash']==expected
    root = Path(__file__).parents[1]/'docs'/'evidence'
    for name in ('ai-trained-vs-search.json','ai-trained-vs-greedy.json'):
        assert json.loads((root/name).read_text())['model_hash']==expected
