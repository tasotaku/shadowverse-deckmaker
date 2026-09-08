"""保存済みの探索資料を、元の識別値を保って小分けに読む。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, NamedTuple

from svdeck.discovery_evidence import JSONDict, digest, read_object


class Section(NamedTuple):
    unit: str
    content: list[Any]
    full_packet_path: str | None


def _load_packet(session: Path, packet_hash: str) -> JSONDict:
    # AI_NOTE: 現在の改訂やDBを読み直さず、指定された保存版とファイル名の識別値だけを照合する。
    if not re.fullmatch(r"[0-9a-f]{64}", packet_hash):
        raise ValueError("packet_hashには保存済みpacketのsha256を指定してください")
    envelope = read_object(session / "packets" / f"{packet_hash}.json")
    data = envelope.get("data")
    if not isinstance(data, dict) or envelope.get("sha256") != packet_hash or digest(data) != packet_hash:
        raise ValueError("packet_hashと保存された資料の識別値が一致しません")
    return data


def _lines(value: object, path: str | None) -> Section:
    # AI_NOTE: 改行を保持して分割するため、ページを順に連結すると元の文章・JSONを復元できる。
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return Section("lines", text.splitlines(keepends=True), path)


def _sections(data: JSONDict) -> dict[str, Section]:
    # AI_NOTE: よく読む資料を独立区分にし、残りの属性も残す。新しい属性が増えても読出しで失わない。
    context: JSONDict = data["context"]
    context_parts = {"cards", "rules", "principles", "known_decks", "ability_keywords", "fulfillment_map"}
    packet_parts = {"context", "instruction", "response_example", "search", "proposal", "previous_reviews", "sources", "history",
                    "review_contexts"}
    return {
        "cards": Section("cards", context["cards"], "data.context.cards"),
        "rules": _lines(context["rules"], "data.context.rules"),
        "keywords": Section("keywords", [{"keyword": key, "text": value}
                                           for key, value in context["ability_keywords"].items()], "data.context.ability_keywords"),
        "principles": _lines(context["principles"], "data.context.principles"),
        "known_decks": Section("decks", context["known_decks"], "data.context.known_decks"),
        "search": Section("questions", data["search"], "data.search"),
        "proposal": _lines(data["proposal"], "data.proposal") if data["proposal"] is not None else Section("lines", [], "data.proposal"),
        "previous_reviews": Section("reviews", data["previous_reviews"], "data.previous_reviews"),
        "review_contexts": Section("reviews", data.get("review_contexts", []),
                                   "data.review_contexts" if "review_contexts" in data else None),
        "history": _lines(data.get("history", []), "data.history" if "history" in data else None),
        # AI_NOTE: 本文を改行保持の配列へ展開し、長い1資料を1項目・1JSON行へ詰め込まない。
        "sources": _lines([{**source, "content": source["content"].splitlines(keepends=True)}
                           for source in data.get("sources", [])], "data.sources" if "sources" in data else None),
        "context_metadata": _lines({key: value for key, value in context.items() if key not in context_parts}, "data.context"),
        "fulfillment_map": _lines(context["fulfillment_map"], "data.context.fulfillment_map"),
        "instruction": _lines(data["instruction"], "data.instruction"),
        "response_example": _lines(data["response_example"], "data.response_example"),
        "packet_metadata": _lines({key: value for key, value in data.items() if key not in packet_parts}, "data"),
    }


def packet_summary(session: Path, packet_hash: str) -> JSONDict:
    # AI_NOTE: 概要に新しいhashを振らず、回答にも読出しにも同じ全文資料の識別値を使わせる。
    data = _load_packet(session, packet_hash)
    return {
        "sha256": packet_hash,
        "packet_path": str((session / "packets" / f"{packet_hash}.json").resolve()),
        "stage": data["stage"],
        "revision": data["revision"],
        "context_hash": data["context_hash"],
        "objective": data["context"]["objective"],
        "instruction": data["instruction"],
        "response_example": data["response_example"],
        "source_usage": data.get("source_usage"),
        "sections": [{"section": name, "unit": section.unit, "total": len(section.content),
                      "full_packet_path": section.full_packet_path}
                     for name, section in _sections(data).items()],
        "reading": "read SESSION PACKET_HASH SECTION --offset 0 --limit 20。"
                   "各区分のnext_offsetがnullになるまで、返された位置から読み進めてください。"
                   "offsetは0始まりです。回答のpacket_hashには上のsha256を使います。",
    }


def read_packet(session: Path, packet_hash: str, section: str, offset: int = 0, limit: int = 20) -> JSONDict:
    # AI_NOTE: 要素・行の区切りと次の位置を返し、空区分や最終ページでも読み落としを判別できるようにする。
    if type(offset) is not int or offset < 0 or type(limit) is not int or limit <= 0:
        raise ValueError("offsetは0以上、limitは1以上の整数を指定してください")
    data = _load_packet(session, packet_hash)
    sections = _sections(data)
    if section not in sections:
        raise ValueError(f"未知の区分です: {section}。利用可能: {', '.join(sections)}")
    selected = sections[section]
    total = len(selected.content)
    if offset > total:
        raise ValueError(f"offsetが総数{total}を超えています")
    content = selected.content[offset:offset + limit]
    end = offset + len(content)
    return {
        "sha256": packet_hash,
        "section": section,
        "unit": selected.unit,
        "offset": offset,
        "limit": limit,
        "total": total,
        "next_offset": end if end < total else None,
        "content": content,
    }
