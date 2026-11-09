import sqlite3, json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dt_time
from collections import defaultdict
from zoneinfo import ZoneInfo

parser = argparse.ArgumentParser(description='Read-only daily Auto Invest operating report, in KST')
parser.add_argument('--date', default=None, help='KST date in YYYY-MM-DD format (default: current KST date)')
args = parser.parse_args()
KST = ZoneInfo('Asia/Seoul')
DAY = args.date or datetime.now(KST).date().isoformat()
try:
    report_date = date.fromisoformat(DAY)
    if report_date.isoformat() != DAY:
        raise ValueError('Use YYYY-MM-DD')
except ValueError:
    parser.error('--date must be a valid date formatted YYYY-MM-DD')
start_kst = datetime.combine(report_date, dt_time.min, tzinfo=KST)
end_kst = start_kst + timedelta(days=1)
START_UTC = start_kst.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
END_UTC = end_kst.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
DB = Path('auto_invest.db').resolve()
if not DB.is_file():
    raise SystemExit(f'DB NOT FOUND: {DB}')
con = sqlite3.connect('file:' + DB.as_posix() + '?mode=ro', uri=True, timeout=3)
con.row_factory = sqlite3.Row
con.execute('PRAGMA query_only=ON')

def schema(t):
    exists = con.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', t)).fetchone()
    return {r['name'] for r in con.execute(f'PRAGMA table_info("{t}")')} if exists else set()

def query(t, wanted, where='', params=(), max_rows=1500):
    present = schema(t)
    fields = [k for k in wanted if k in present]
    if not fields:
        return []
    sql = f'SELECT {", ".join(fields)} FROM "{t}"'
    if where:
        sql += ' WHERE ' + where
    sql += ' ORDER BY id DESC LIMIT ?' if 'id' in present else ' LIMIT ?'
    return [dict(r) for r in con.execute(sql, (*params, max_rows)).fetchall()]

def time_filter(field='created_at'):
    return f"replace(substr({field},1,19),'T',' ') >= ? AND replace(substr({field},1,19),'T',' ') < ?"

def short(v, size=125):
    if v is None: return '-'
    s = str(v).replace('\n', ' ').replace('\r',' ')
    return s[:size] + ('...' if len(s)>size else '')

def kst(v):
    if not v: return '-'
    try:
        d = datetime.fromisoformat(str(v).replace('Z','+00:00'))
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone(timedelta(hours=9))).strftime('%m-%d %H:%M KST')
    except (ValueError, TypeError): return short(v)

INTERESTING = {
    'reason','block_reason','skip_reason','status','result','action','execution_status',
    'entry_ready','should_trade','selected_by_a_top5','quant_a_rank',
    'quant_c_status','quant_c_score','quant_c_threshold','quant_c_gate_passed',
    'gpt_analysis_status','gpt_buy_score','gpt_buy_score_threshold',
    'gpt_buy_score_gate_passed','a_top5_score_gate_reason',
    'final_buy_score','final_entry_score','final_selected','approved_by_risk',
    'risk_flags','gating_notes','broker_submit_called','real_order_submitted',
    'daily_trade_count','available_cash','requested_notional','approved_notional',
}
def diag(raw):
    try: obj=json.loads(raw) if isinstance(raw,str) else raw
    except (TypeError,ValueError): return {}
    found={}
    def walk(x, prefix='', level=0):
        if level > 3 or len(found) >= 18: return
        if isinstance(x, dict):
            for k,v in x.items():
                if len(found)>=18: return
                key=str(k)
                if key in INTERESTING and not isinstance(v,(dict,list)):
                    found[(prefix+'.' if prefix else '')+key]=short(v,90)
                elif key in INTERESTING and isinstance(v,list):
                    found[(prefix+'.' if prefix else '')+key]=short(v[:5],180)
                if isinstance(v,dict) and level<3:
                    walk(v,key,level+1)
        elif isinstance(x,list):
            for v in x[:2]: walk(v,prefix,level+1)
    walk(obj)
    return found

def heading(s): print('\n' + '='*17 + ' ' + s + ' ' + '='*17)

print('DB:', DB, ' | KST date:', DAY, ' | READ-ONLY / NO API / NO ORDERS')
users = query('users',['id','username','role'],max_rows=200)
admin = next((r for r in users if r.get('id')==1 and r.get('role')=='admin'),None)
admin = admin or next((r for r in users if r.get('role')=='admin'),None)
test = next((r for r in users if str(r.get('username','')).lower() in ('test1','test01')),None)
test = test or next((r for r in users if r.get('id')==2 and (not admin or r['id']!=admin['id'])),None)
accounts=[('ADMIN',admin),('TEST01',test)]
heading('ACCOUNTS')
for label,u in accounts:
    print(label, {'id':u['id'],'username':u['username'],'role':u['role']} if u else 'NOT FOUND')

heading('CURRENT ACCOUNT SETTINGS (NOT HISTORICAL)')
for label,u in accounts:
    if not u:continue
    r=query('user_trading_settings',['id','user_id','enabled','trading_mode','live_trading_enabled','auto_trading_enabled','auto_trading_provider','kill_switch','max_daily_trades','max_open_positions','no_new_entry_after'],where='user_id=?',params=(u['id'],),max_rows=1)
    print(label, r[0] if r else 'no settings row')

heading('SCHEDULER SLOT CLAIMS')
slots=query('user_auto_trading_slot_claims',['id','user_id','trading_date','scheduler_slot','status','result','reason','run_key','created_at','updated_at'],where='trading_date=?',params=(DAY,))
for label,u in accounts:
    if not u:continue
    group=sorted((r for r in slots if r.get('user_id')==u['id']),key=lambda r:r.get('id',0))
    print(f'{label}: {len(group)} slots')
    for r in group[-10:]: print(' ',r['scheduler_slot'],r['status'],r.get('result'),short(r.get('reason')),kst(r.get('updated_at')),'run=',r.get('run_key'))

heading('TRADE RUNS')
runs=query('trade_run_logs',['id','owner_user_id','created_at','run_key','trigger_source','mode','symbol','stage','result','reason','signal_id','order_id','response_payload'],time_filter(),(START_UTC,END_UTC))
for label,u in accounts:
    if not u:continue
    group=sorted((r for r in runs if r.get('owner_user_id')==u['id']),key=lambda r:r.get('id',0))
    print(f'{label}: {len(group)} run rows')
    for r in group[-14:]:
        print(' ',r['id'],kst(r['created_at']),r.get('trigger_source'),r.get('mode'),short(r.get('symbol')),r.get('result'),'reason='+short(r.get('reason')),'order_id='+str(r.get('order_id')))
        if r in group[-3:]:
            details=diag(r.get('response_payload'))
            if details:print('    response:',details)
unknown=[r for r in runs if r.get('owner_user_id') is None]
print(f'UNASSIGNED run rows: {len(unknown)} (do not assume ADMIN)')
for r in sorted(unknown,key=lambda r:r.get('id',0))[-8:]:
    print(' ',r['id'],kst(r['created_at']),r.get('trigger_source'),r.get('mode'),r.get('result'),short(r.get('reason')))

heading('AI / GPT / FINAL CANDIDATES - LATEST SLOT PER ACCOUNT')
candidates=query('automation_profile_ai_candidate_results',[
    'id','owner_user_id','profile_id','snapshot_id','run_id','snapshot_date','scheduler_slot','symbol',
    'snapshot_rank','runtime_quant_rank','runtime_quant_buy_score','gpt_target_rank','gpt_used',
    'gpt_analysis_status','ai_buy_score','ai_sell_score','final_buy_score','final_sell_score',
    'final_rank','final_selected','diagnostics_json','created_at'],
    'snapshot_date=?',(DAY,),max_rows=2500)
for label,u in accounts:
    if not u:continue
    owned=[r for r in candidates if r.get('owner_user_id')==u['id']]
    groups=defaultdict(list)
    for r in owned: groups[(r.get('profile_id'),r.get('scheduler_slot'),r.get('run_id'),r.get('snapshot_id'))].append(r)
    print(f'{label}: {len(owned)} candidate rows / {len(groups)} groups')
    ordered=sorted(groups.items(),key=lambda it:max((str(v.get('created_at')) for v in it[1]),default=''),reverse=True)
    for key,grp in ordered[:4]:
        completed=sum(str(x.get('gpt_analysis_status')).lower()=='completed' for x in grp)
        selected=[x for x in grp if x.get('final_selected')]
        print(' SLOT',key,'rows='+str(len(grp)),'GPT_completed='+str(completed),'FINAL_selected='+str(len(selected)))
    if ordered:
        key,grp=ordered[0]
        grp.sort(key=lambda r:(0 if r.get('final_selected') else 1,0 if r.get('gpt_target_rank') else 1,r.get('final_rank') or 9999,r.get('runtime_quant_rank') or 9999))
        show=grp[:12]
        for r in grp[12:]:
            if r.get('final_selected') or (r.get('final_buy_score') is not None and r.get('final_buy_score')>=65):show.append(r)
        for r in show[:20]:
            print('  ',r['symbol'],'A=',r.get('runtime_quant_buy_score'),'A_rank=',r.get('runtime_quant_rank'),
              'GPT=',r.get('ai_buy_score'),r.get('gpt_analysis_status'),'used=',r.get('gpt_used'),
              'FINAL=',r.get('final_buy_score'),'selected=',r.get('final_selected'))
            d=diag(r.get('diagnostics_json'))
            if d:print('     GATES:',d)

heading('C OBSERVATIONS - LATEST SLOT PER SOURCE')
obs=query('quant_ab_observations',[
    'id','trigger_source','decision_slot','observed_at','symbol','a_rank','a_quant_buy_score','a_gpt_buy_score','a_final_score',
    'c_reversal_score','data_quality_c','c_reason','base_c_min','shadow_regime_c_min','market_regime_stage',
    'base_c_pass','shadow_regime_c_pass'],
    "substr(coalesce(decision_slot,observed_at,''),1,10)=?",(DAY,),max_rows=2500)
for label,src in [('ADMIN*','automation_scheduler'),('TEST01*','user_scheduler')]:
    own=[r for r in obs if r.get('trigger_source')==src]
    grouped=defaultdict(list)
    for r in own: grouped[r.get('decision_slot') or r.get('observed_at')].append(r)
    print(label,'source-based inference only, rows=',len(own),'slots=',len(grouped))
    for stamp,group in sorted(grouped.items(),key=lambda x:str(x[0]),reverse=True)[:4]:
        scored=[r for r in group if r.get('c_reversal_score') is not None]
        print(' ',stamp,'rows=',len(group),'C_scored=',len(scored),'C_quality_1=',sum(r.get('data_quality_c')==1 for r in scored),'A_final=',sum(r.get('a_final_score') is not None for r in group))
        for r in sorted(scored,key=lambda x:x.get('c_reversal_score') or -1,reverse=True)[:5]:
            print('   ',r['symbol'],'A=',r.get('a_quant_buy_score'),'C=',r.get('c_reversal_score'),'quality=',r.get('data_quality_c'),'GPT=',r.get('a_gpt_buy_score'),'FINAL=',r.get('a_final_score'),'regime=',r.get('market_regime_stage'),'C_min=',r.get('base_c_min'))

heading('ORDERS / FILLS (CREATED OR UPDATED TODAY)')
order_fields=['id','owner_user_id','broker','market','symbol','side','qty','notional','requested_qty','filled_qty','filled_avg_price','realized_pl','internal_status','broker_status','kis_odno','created_at','updated_at']
order_where=f'({time_filter("created_at")}) OR ({time_filter("updated_at")})'
orders=query('orders',order_fields,order_where,(START_UTC,END_UTC,START_UTC,END_UTC))
for label,u in accounts:
    if not u:continue
    group=sorted((r for r in orders if r.get('owner_user_id')==u['id']),key=lambda r:r.get('id',0))
    print(f'{label}: {len(group)} order rows')
    for r in group[-16:]:
        print(' ',r['id'],r.get('broker'),r.get('symbol'),r.get('side'),'qty=',r.get('qty'),'filled=',r.get('filled_qty'),'status=',r.get('internal_status'),'broker_status=',r.get('broker_status'),'created=',kst(r.get('created_at')),'updated=',kst(r.get('updated_at')))
print('UNASSIGNED orders:',sum(r.get('owner_user_id') is None for r in orders),'(unattributed; inspect only if needed)')

heading('BUY EXECUTION ATTEMPTS / PROMOTIONS (NOT OWNER-SCOPED)')
for table,fields in [
 ('strategy_live_auto_buy_attempts',['id','created_at','symbol','active_profile','status','trigger_source','block_reason','risk_flags','gating_notes','related_order_id','requested_notional_krw','approved_notional_krw']),
 ('strategy_auto_buy_promotions',['id','created_at','symbol','active_profile','status','block_reason','promotion_reason','final_score','promoted_to_live_attempt_id','related_live_order_id']),
]:
    group=sorted(query(table,fields,time_filter(),(START_UTC,END_UTC)),key=lambda r:r.get('id',0))
    print(table,'count=',len(group),'(DO NOT infer owner from this table)')
    for r in group[-14:]:
        print(' ',r.get('id'),kst(r.get('created_at')),r.get('symbol'),r.get('active_profile'),r.get('status'),'reason=',short(r.get('block_reason') or r.get('promotion_reason')),'order=',r.get('related_order_id',r.get('related_live_order_id')))

heading('LAST ADMIN CYCLE - SUMMARY')
if admin:
    ar=sorted((r for r in runs if r.get('owner_user_id')==admin['id']),key=lambda r:r.get('id',0),reverse=True)
    for r in ar[:3]:
        print('run_id=',r['id'],'KST=',kst(r.get('created_at')),'status=',r.get('result'),'reason=',r.get('reason'),'order_id=',r.get('order_id'))
        print('  response gate evidence:',diag(r.get('response_payload')))
    if not ar:print('No owner-scoped admin run today; inspect unassigned runs above.')
print('\nREAD COMPLETE. No DB writes or broker API calls.')
con.close()
