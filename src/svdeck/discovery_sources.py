"""比較資料や観察を、内容で識別して追記専用で保存する。"""

from __future__ import annotations

from pathlib import Path

from svdeck.discovery_evidence import JSONDict, digest, read_object, write_new

FIELDS = {"title", "kind", "location", "observed_at", "content", "limitations"}


def validate_source(value: object) -> JSONDict:
    # AI_NOTE: 全項目を境界で検査し、本文・観察時点・限界を黙って落とさない。
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("資料にはtitle/kind/location/observed_at/content/limitationsを指定してください")
    for field in ("title", "kind", "location", "content"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"資料の{field}には空でない文字列が必要です")
    observed = value["observed_at"]
    if observed is not None and (not isinstance(observed, str) or not observed.strip()):
        raise ValueError("資料のobserved_atはnullまたは空でない文字列です")
    limits = value["limitations"]
    if not isinstance(limits, list) or any(not isinstance(v, str) or not v.strip() for v in limits):
        raise ValueError("資料のlimitationsは空でない文字列の配列です。制限の記載がなければ空配列です")
    return value


def load_sources(session: Path) -> list[JSONDict]:
    # AI_NOTE: 保存内容とファイル名の両方を検査し、違う正常資料への差し替えも検出する。
    sources = []
    for path in sorted((session / "sources").glob("*.json")):
        envelope = read_object(path)
        value = validate_source(envelope.get("data"))
        key = digest(value)
        if envelope.get("sha256") != key or path.stem != key:
            raise ValueError(f"資料の保存内容・ファイル名の識別値が一致しません: {path}")
        sources.append({"source_hash": key, **value})
    return sources


def save_sources(session: Path, payload: JSONDict) -> JSONDict:
    # AI_NOTE: 入力全体と保存済み資料の検証後だけ追記し、入力途中の失敗では何も保存しない。
    if set(payload) != {"sources"} or not isinstance(payload["sources"], list):
        raise ValueError("sourcesに資料オブジェクトの配列を指定してください")
    values = [validate_source(value) for value in payload["sources"]]
    existing = {source["source_hash"] for source in load_sources(session)}
    unique = {digest(value): value for value in values}
    added = [key for key in unique if key not in existing]
    if added:
        folder = session / "sources"
        folder.mkdir(exist_ok=True)
        for key in added:
            write_new(folder / f"{key}.json", {"sha256": key, "data": unique[key]})
    return {"added": added, "existing": [key for key in unique if key in existing],
            "total": len(existing) + len(added),
            "next": "新しいpacketには追加資料が入ります。保存済みのpacket・改訂・評価は変わりません"}
