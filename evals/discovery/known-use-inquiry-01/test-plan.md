# 明示した先例あり候補の後続調査を検査する

正常系：test/knownから調査→別照合→元評価を保持した資料保存。既存test/unconfirmedと番号指定は保持。
境界：元評価のknownと識別を変えず、出発点をknown-use-prevalenceへ記録。自動cycleはknownを従来どおり自動調査しない。
異常系：develop/drop/unknown、differentiated、古い改訂、誤識別、未提出・期限停止を従来どおり拒否または失敗として保存。

既存の後続調査・番号指定・自動接続・公開提出・引き渡し検査を実行する。旧test/known拒否ケースは新仕様の完走・保持ケースに置き換え、他の拒否条件を維持する。
