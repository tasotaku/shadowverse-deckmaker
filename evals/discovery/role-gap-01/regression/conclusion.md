Aは指定状態で13点決着が成立する。余白のしるしで紙梯子を0PPにし、守衛庫で元コスト12の番兵を場へ生成、紙梯子で手札へ戻し、金環の対句を使う。支払は1+4+0+4=9PP、手札は8→7→6→6→5、相手体力13→0、最後の自場は空。通常の金環4点＋火花4点（8PP、相手残5）より5点多い。軽減なしでは10PP必要で1PP不足、生成だけでは手札条件が未達。

Bは指定状態で13点に届かず、上限8点・相手残5。番兵の元コストは9で、回収しても金環の「12以上」を満たさない。入手可能な全フォロワーは元コスト2・3・9で、元コスト上昇、別の打点、即時攻撃、スペル再使用は提供本文にない。通常の金環＋火花で8PP・8点。しるしを金環に使うと、9PPで同じ8点に番帳2/2守護を追加できるが、手札をさらに2枚使う。番兵回収枝は9PPで4点に留まる。これらは各札の回復・防御用途まで否定するものではない。

使用資料：input-a.json / input-b.jsonの目的・instruction・response_example、および各caseの公開read入口から得たcards全9枚（本文・進化・参照先・種族・note）、rules全117行、principles全526行、fulfillment_map全234行、context_metadata、packet_metadata、keywords、known_decks、search、sources。全ページをnext_offset=nullまで取得し、read-a.json / read-b.jsonへ保存した。keywords・known_decks・searchは0件、sourcesは空。カードのsource_urlを含め外部Webは参照していない。

資料識別値：
- A: d6f0241aa1063afae260f078aa897ada90a5cdfa0f0d65f76ecb4ab8e523b683
- B: 47c88e53e21e76eb015a54a1c0d86a1e0b5e02424717222e7e25520a3e45b5d7

保存・照合：proposal-a.jsonをcase-a、proposal-b.jsonをcase-bへpublic.py submitで正式保存し、両方revision 1。届け先のpublic.py reportを取得したreport-a.json / report-b.jsonで、revision・親revision・packet_hash・title・hypothesis・change・questions・uncertaintiesを照合した。総数2＝正式保存・report照合済み2。引用は各入力の本文と完全一致を確認済み。reportにはroles・steps・plan全文は表示されないため、その全文の再取得照合は未実施（提出ファイルに記録）。照合結果はverification.json。

未確認：実対戦、勝率、40枚構築の採用配分、引き込み、新規性、方式の採用価値。守護の公式定義は未提供で具体的な防御量は計上していない。正式評価は指示どおり未実施で、両reportとも評価記録は空。旧回答・正解・ソースコード・他の作業先は探索資料に使わず、別担当も起動していない。
