# v2 revision decision

TEST_SPEC_ISSUEを受理する。v1 T3 U3の「前面」はbrowser tabとOS windowの観測対象が曖昧で、OS前面としての必須検証はこの実行環境の観測能力を超える。公開対戦ラボでlookaheadを選び一手進めて限界を読むという利用者目標には、OS全体での前面化の明示要件はない。

v2ではT3 U3の対象をブラウザー内の選択タブとDOM文書可視性として明記する。selectedTab、document.visibilityState、選択欄の値を操作区間で直接記録し、visibilitychangeを時刻付きで記録する。OS前面・他アプリとの重なり・OS keyboard focusはblind spotとして残し、ブラウザー観測からOS状態の合格を推定しない。

30秒上限、同一対戦タブの継続、lookahead選択保持、不要な別タブ遷移禁止、手動再読込不要は維持する。T1/T2、T3のほかの条件、操作数、スクロール上限、予算、保存状態なしは変更しない。保存状態の隔離は専用origin/port等の実行手段で扱えるため、条件改訂の理由にしない。

独立性: 本担当が参照したのは元の目標、固定spec v1とlock、skill/contract、環境の観測制約のみ。製品source、diff、製品の実行結果・過去判定は参照していない。条件が厳しいことや製品の失敗を改訂理由にしていない。

変更範囲はversion、T3 U3、coverage.blind_spotsへの追加、revisionメタデータのみ。v1とそのlockは保持する。
