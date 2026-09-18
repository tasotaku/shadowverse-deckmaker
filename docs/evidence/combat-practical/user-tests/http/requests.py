from client import *
from fractions import Fraction as F
weights=dict.fromkeys(['leader','attack','health','body','hand','pp','ep','sep','keyword','win','own_board_health'],0);weights['own_board_health']=1
for name,cid,opt in [('adaptive','random-two-ward-adaptive-anchor',{}),('slot','slot-pp-evolve',{}),('split','split-oldest-first',{}),('objective-lethal','objective-preserve-versus-win',{'objective':'lethal','weights':weights}),('objective-value','objective-preserve-versus-win',{'objective':'value','weights':weights}),('limited','random-half-anchor',{'max_states':1}),('invalid','random-half-anchor',{'max_states':0})]:
 c=cases[cid]; r=post(name,'/api/combat-practical',{'record':Battle(c['state'],c['cards']).export(),'options':opt})
 print(name,r.get('win_probability_exact'),r.get('expected_value_exact'),r.get('recommended_action'),r.get('complete'),r.get('error'),len(r.get('policy',[])),flush=True)
r=post('recovery','/api/combat-practical',{'record':Battle({'players':[{'ep':0,'sep':0},{'ep':0,'sep':0}]},{}).export()})
print('recovery',r.get('win_probability_exact'),r.get('complete'),flush=True)
