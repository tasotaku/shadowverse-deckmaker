import json
from pathlib import Path
from datetime import datetime, timezone
W=Path('/tmp/sv-pp-comparison-01/a/work')
x=json.loads((W/'calc-input.json').read_text())
results=[]
def form(symbol,offset):
    return symbol if offset==0 else f'{symbol}{offset:+}'
for plan in x['plans']:
    current=x['common_start']['current_pp']; extra=x['common_start']['extra_remaining']; rows=[]
    for a in plan['t8']:
        before=current;extra_before=extra
        current+=a['delta'];extra=a.get('extra_after',extra)
        rows.append({'row':a['row'],'turn':8,'action':a['label'],'current_before':before,'delta':a['delta'],'current_after':current,'extra_before':extra_before,'extra_after':extra,'available_after':current+extra,'affordable':before>=-a['delta'] if a['delta']<0 else True})
    t8_end={'current_pp':current,'extra_remaining':extra,'available_pp':current+extra}
    assert extra==plan['extra_at_t9']
    prefix='G' if plan['name']=='ゴッデス' else 'L'
    symbol=plan['t9_start']['symbol']; current=plan['t9_start']['numeric_case'];offset=0
    rows.append({'row':prefix+'6','turn':9,'action':'T9開始（数値は開始9の場合）','current_before':None,'delta':None,'current_after':current,'symbolic_after':symbol,'extra_after':extra,'available_after':current+extra,'symbolic_available_after':form(symbol,extra),'affordable':None})
    for a in plan['t9']:
        before=current; offset_before=offset
        current+=a['delta'];offset+=a['delta']
        rows.append({'row':a['row'],'turn':9,'action':a['label'],'current_before':before,'symbolic_before':form(symbol,offset_before),'delta':a['delta'],'current_after':current,'symbolic_after':form(symbol,offset),'extra_before':extra,'extra_after':extra,'available_after':current+extra,'symbolic_available_after':form(symbol,offset+extra),'affordable':before>=-a['delta'] if a['delta']<0 else True})
    results.append({'name':plan['name'],'rows':rows,'t8_end':t8_end,'t9_end_numeric_case':{'condition':'T9開始9PPで、原文に記された増減だけを使う','current_pp':current,'extra_remaining':extra,'available_pp':current+extra},'t9_end_symbolic':{'current_pp':form(symbol,offset),'available_pp':form(symbol,offset+extra),'minimum_start_pp_without_adding_actions':-offset},'all_recorded_numeric_payments_affordable':all(r['affordable'] is not False for r in rows)})
a,b=results
out={'method':'A','plans':results,'difference_goddess_minus_luria':{'numeric_current_pp':a['t9_end_numeric_case']['current_pp']-b['t9_end_numeric_case']['current_pp'],'numeric_available_pp':a['t9_end_numeric_case']['available_pp']-b['t9_end_numeric_case']['available_pp'],'symbolic_current_pp':'g-l+2','symbolic_available_pp':'g-l+1','condition_for_fixed_differences':'両側のT9開始PPが同じなら現在PP差2、追加分込みの差1。開始PPが異なる場合の固定差は断定しない。'},'limitations':x['limitations']}
(W/'calc-output.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
lines=['|行|ターン・行動|現在PP 前→後（T9開始9の場合）|未使用の追加分|追加分込みで使える量|T9の記号結果|','|---|---|---|---:|---:|---|']
for plan in results:
    for r in plan['rows']:
        before='—' if r['current_before'] is None else r['current_before']
        lines.append(f"|{r['row']}|T{r['turn']} {r['action']}|{before}→{r['current_after']}|{r['extra_after']}|{r['available_after']}|{r.get('symbolic_after','—')}|")
(W/'calculation-table.md').write_text('\n'.join(lines)+'\n')
e=json.loads((W/'execution.json').read_text())
e['milestones']['calculation_complete']=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
(W/'execution.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ends':[{k:v for k,v in z.items() if k!='rows'} for z in results],'difference':out['difference_goddess_minus_luria']},ensure_ascii=False,indent=2))
