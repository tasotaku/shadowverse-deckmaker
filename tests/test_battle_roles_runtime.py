"""Roles decisions use the existing HTTP and replay contracts."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from svdeck.battle_env.battle import Battle, replay
from svdeck.battle_env.battle_server import create_server


@pytest.fixture
def server_url() -> Iterator[str]:
    # AI_NOTE: 利用中の画面に触れず、独立した一時ポートで通常のHTTP入口を検査する。
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def post(url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    # AI_NOTE: 公開APIへJSONを送り、内部の選手呼出しを代用せず保存結果を読む。
    request = urllib.request.Request(url+path, json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request) as response:
        result: dict[str, Any] = json.load(response)
    return result


def test_roles_step_and_replay_keep_judgment(server_url: str) -> None:
    # AI_NOTE: 新方式と候補数設定が一手APIから到達し、保存後も判断の同一性を保つ。
    battle = Battle({'players': [{'board': [{'id': 'a', 'card_id': 'test-body'}], 'deck': ['test-body']*3},
                                {'health': 2, 'deck': ['test-body']*3}]})
    response = post(server_url, '/api/ai-step', {'record': battle.export(), 'policy': 'roles',
                                              'options': {'role_k': 3, 'turns': 1, 'max_nodes': 40, 'seconds': .2, 'seed': 9}})
    decision = response['decision']
    assert decision['policy'] == 'roles'
    assert decision['action'] in battle.legal_actions()
    assert decision['role_search']['role_k'] == 3
    assert decision['uncertain'] and not decision['optimal']
    assert not decision['proven_win']
    restored = post(server_url, '/api/replay', {'record': response['record'], 'cursor': 1})
    assert restored['record']['frames'][0]['decision'] == decision
    assert replay(restored['record']).state == response['state']


@pytest.mark.parametrize('role_k', [0, 21, True, 1.5, '5'])
def test_roles_api_rejects_invalid_candidate_count(server_url: str, role_k: Any) -> None:
    # AI_NOTE: APIは候補数を勝手に丸めず、公開設定の型・範囲違反を入力エラーとして返す。
    with pytest.raises(urllib.error.HTTPError) as error:
        post(server_url, '/api/ai-step', {'record': Battle({}).export(), 'policy': 'roles', 'options': {'role_k': role_k}})
    assert error.value.code == 400
