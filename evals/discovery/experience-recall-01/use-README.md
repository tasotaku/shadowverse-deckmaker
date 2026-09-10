# 保存経験を探す公開入口

この作業先の `./sv` は、指定された本体の保存先を読み取り専用で参照します。

- `./sv recall --query リッター`：案名・カード名・役割・計画・未確認・評価理由を文字列検索。空白区切りは全語一致。
- `./sv recall --card-id 10423310 --card-id 10421130`：両カードが正式案の役割にあるものを探す。
- `--class ロイヤル --format rotation --limit 5` で絞れます。件数制限は1〜50です。省略件数がある場合は絞り直すか件数を増やしてください。
- `./sv read SESSION PACKET_HASH proposal --offset 0 --limit 20`：該当保存版の案を行単位で再読。`next_offset`がnullになるまで続けると全文です。
- `./sv read SESSION PACKET_HASH sources --offset N --limit N`：元資料を行単位で再読。
- `./sv read SESSION PACKET_HASH cards --offset N --limit 1`：カード本文を再読。検索結果のcards.read_offsetがその位置です。

検索結果のproposalは案全文、reviewsは正式評価全文、originsは保存場所と評価時の資料対応です。同じproposal_hashの複製はまとめますが、別の改訂や評価は別々です。readではレビューのpacket_hashを選ぶとその評価対象の案を読めます。考案入力のpacket_hashはその案を提出する前の入力なので、proposalには親案が入っています。
エラーがある場合はcomplete=falseの部分結果です。保存時点の評価や資料であり、現在の能力・普及・強さを証明しません。別の探索へ資料を自動添付しません。
