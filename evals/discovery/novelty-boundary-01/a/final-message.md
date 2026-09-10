{
  "cases": [
    {
      "id": "c1",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "同じ役割・手順の先行例1件は確認済みだが、一般への普及は不明。先行例の存在だけではknownとせず、標準用法との差も確認できないため独自性は未確認。",
      "evidence_ids": ["s1"],
      "next_question": "同じ役割・手順は、現行形式・同時点の攻略記事や大会構築でどの程度普及しているか。"
    },
    {
      "id": "c2",
      "novelty": "known",
      "procedure": "conditional",
      "value": "test",
      "finding": "独立した攻略サイト3件で同じ役割・配分・手順が標準掲載され、大会40構築中25構築でも使用説明が一致する。一般に広まった用法と判断でき、提案固有の差は示されていない。",
      "evidence_ids": ["s2"],
      "next_question": ""
    },
    {
      "id": "c3",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "X・Yの先行採用と標準記事1件の手動起爆は確認済み。ただし先行例の全配分・手順が未取得で、自然消滅と防御への行動配分が同用途として普及しているか比較できない。カードの同居だけでは用法の既知性も差別化も確定しない。",
      "evidence_ids": ["s3"],
      "next_question": "先行例は自然消滅にYを合わせて防御へ行動量を回す手順か。また、その用法は現行形式で普及しているか。"
    },
    {
      "id": "c4",
      "novelty": "differentiated",
      "procedure": "conditional",
      "value": "test",
      "finding": "s4の現行形式・当月の独立攻略サイト3件30リスト・使い方記事・大会一覧との比較で、標準の手動起爆から自然消滅へ変え、防御に行動を回す具体的な差が確認済み。カード名・自然消滅・起爆・防御を組み合わせた個人記事検索でも同じ接続は未取得。観測範囲内の差別化であり、世界初や全情報での不存在は主張しない。",
      "evidence_ids": ["s4"],
      "next_question": ""
    },
    {
      "id": "c5",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "ローカル同居0件とカード名2語の検索ヒット0件のみ確認済み。比較元の使い方本文、異表記・用途での検索が欠けており、検索不発から独自性は認定できない。",
      "evidence_ids": ["s5"],
      "next_question": "異表記や補充用途でも調べ、比較元の本文を確認した場合、同じ使い方の普及または具体的な用法の差を確認できるか。"
    },
    {
      "id": "c6",
      "novelty": "known",
      "procedure": "conditional",
      "value": "test",
      "finding": "独立した攻略サイト3件で同じ役割・行動順が標準掲載済み。Bを3枚から2枚へ減らしても要求達成手段・利益は同じで、枚数差だけでは使い方の独自性を示さない。",
      "evidence_ids": ["s6"],
      "next_question": ""
    }
  ],
  "scope": "作業先のinstruction.txt・principles.txt・cases.jsonのみを入力とした、全6件の独立した仮想判定。s1〜s6は各仮想状況内で正しい観測として扱った。実Web調査・実カード調査・追加調査は行っていない。differentiatedは記載された観測範囲内の用法差を示し、全世界の未踏性を保証しない。手順・価値に関する追加事実はないため、全件でother_axesのconditional・testを継承した。"
}