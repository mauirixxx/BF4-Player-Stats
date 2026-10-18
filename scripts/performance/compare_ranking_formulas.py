"""Pure-Python parity checks of independent canonical vehicle aggregation paths."""
from decimal import Decimal
from bf4ps.ranking_backfill import FAMILIES, ZERO_ONLY

def reference(rows, item):
    relevant=[r for r in rows if FAMILIES.get(r[1],(r[1],"max"))[0]==item and r[1] not in ZERO_ONLY]
    grouped={}
    for soldier,vehicle,kills,seconds in relevant:
        grouped.setdefault(soldier,[]).append((kills,seconds))
    mode=FAMILIES.get(item,(item,"max"))[1]
    return {soldier:(sum(k for k,t in v) if mode=="sum" else max(k for k,t in v),sum(t for k,t in v) if mode=="sum" else max(t for k,t in v)) for soldier,v in grouped.items()}

def derived(rows,item):
    by_variant={}
    for soldier,vehicle,kills,seconds in rows:
        family,mode=FAMILIES.get(vehicle,(vehicle,"max"))
        if vehicle in ZERO_ONLY or family!=item:continue
        key=(soldier,vehicle)
        old=by_variant.get(key,(0,0))
        by_variant[key]=(max(old[0],kills),max(old[1],seconds))
    grouped={}
    for (soldier,vehicle),pair in by_variant.items():grouped.setdefault(soldier,[]).append(pair)
    mode=FAMILIES.get(item,(item,"max"))[1]
    return {soldier:(sum(k for k,t in v) if mode=="sum" else max(k for k,t in v),sum(t for k,t in v) if mode=="sum" else max(t for k,t in v)) for soldier,v in grouped.items()}

rows=[(1,1,10,100),(1,73,20,200),(1,2,5,60),(1,30,7,120),(2,1,15,60),(2,2,6,60),(2,30,6,60),(3,1,1,20)]
for family in sorted(set(c for c,m in FAMILIES.values())):
    assert reference(rows,family)==derived(rows,family),family
print("PASS: all",len(set(c for c,m in FAMILIES.values())),"canonical vehicle family mappings match independent formula")
