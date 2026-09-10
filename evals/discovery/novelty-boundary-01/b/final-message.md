{
  "cases": [
    {
      "id": "c1",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "個人記事1件で役割・手順が一致する先例は確認済み。ただし一般への普及を示す情報はなく、先例の存在だけではknownにできない。一般的な使い方との差と普及状況の材料も不足し、differentiatedにもできない。",
      "evidence_ids": ["s1"],
      "next_question": "同じ使い方は現行形式・同時点でどの程度普及しており、一般的な使い方と実質的な差があるか。"
    },
    {
      "id": "c2",
      "novelty": "known",
      "procedure": "conditional",
      "value": "test",
      "finding": "独立した攻略サイト3件で役割・配分・手順が標準的な決着手段として一致し、同期間の大会40構築中25構築でも構成と使用説明が一致する。同用途の一般的な普及を裏付けるためknown。今回の独自性判定に必要な不足はない。",
      "evidence_ids": ["s2"],
      "next_question": ""
    },
    {
      "id": "c3",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "取得済みの標準記事1件の手動起爆に対し、提案は自然消滅と防御への行動配分を意図する。ただし先行記事はX・Yの採用しか確認できず、全配分と手順が未取得で同用途か不明。同用途の普及状況も不明なため、同居だけでknownにも、差の主張だけでdifferentiatedにもできない。",
      "evidence_ids": ["s3"],
      "next_question": "先行記事の全配分・行動手順は自然消滅と防御への行動配分を含むか。また、この用途は現行形式でどの程度普及しているか。"
    },
    {
      "id": "c4",
      "novelty": "differentiated",
      "procedure": "conditional",
      "value": "test",
      "finding": "s4の仮想観測では、現行形式・当月の独立攻略サイト3件の当該型30リストと使い方記事、同期間の大会一覧を比較済み。標準の手動起爆に対し、自然消滅へ打点を合わせて行動を防御へ回す実質差を、起動順・枠・失う処理・得る防御まで確認できる。カード名・自然消滅・起爆・防御の組合せによる個人記事検索でも同じ接続は取得されておらず、この範囲でdifferentiated。世界全体の投稿・非公開構築・別言語の全情報は未確認だが、判定に全世界の未普及証明は要しない。",
      "evidence_ids": ["s4"],
      "next_question": ""
    },
    {
      "id": "c5",
      "novelty": "unconfirmed",
      "procedure": "conditional",
      "value": "test",
      "finding": "ローカル同居0件とカード名2語の検索ヒット0件だけが確認済み。比較元の使い方本文がなく、異表記・用途での検索も未実施で、実質的な使い方の差と同用途の普及状況を判断できない。検索不発は独自性の根拠にならない。",
      "evidence_ids": ["s5"],
      "next_question": "比較元の使い方本文と異表記・補充用途の観測から、提案の実質差および同用途の普及状況を確認できるか。"
    },
    {
      "id": "c6",
      "novelty": "known",
      "procedure": "conditional",
      "value": "test",
      "finding": "独立した攻略サイト3件で同じ役割・行動順が標準的な決着として掲載され、同用途の普及が確認済み。Bを3枚から2枚へ減らしても役割・要求達成手段・行動順・利益は同じで、枚数差だけでは実質的な差にならない。今回の独自性判定に必要な不足はない。",
      "evidence_ids": ["s6"],
      "next_question": ""
    }
  ],
  "scope": "instruction.txt・principles.txt・cases.jsonのみを入力として全6件を独立に判定した。証拠記述は仮想状況内の正しい観測として扱ったもので、実Web調査ではなく、外部検索・実カード調査は行っていない。資料中のカード名を実カードと扱っていない。調査範囲と出典は各findingおよびevidence_idsに記録した。他の作業先・元リポジトリ・過去評価・期待回答・別担当の回答は参照していない。手順の成立と試す価値に関する追加事実はないため、全件でother_axesのprocedure=conditional、value=testを引き継いだ。"
}