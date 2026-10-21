"""Reproduce the coefficient-hypothesis evidence from an owner-supplied sample.

Coincident positions are evidence to compare, never a command to weld records.
The best hypothesis remains INFERRED until source-runtime execution is verified.
"""
import argparse,itertools,json,struct
from collections import defaultdict,Counter
from pathlib import Path
import numpy as np
from tools.wwe13_wii_inspect import read_model_header,read_pach,digest


def investigate(data):
    if digest(data)!='feeea42460893cf577b3aa2ffadb239462538be18e822e33d051e096445df542':raise ValueError('Inspected ch145 sample required')
    records=[]
    for bundle,start in enumerate((0x4000,0x48000)):
        sections={s['id']:s['raw']for s in read_pach(data,start)['sections']}
        for sid in (2,10000):
            payload=sections[sid];header=read_model_header(payload);raw=payload[24:]
            u=lambda a:struct.unpack_from('>I',raw,a)[0]
            points=np.frombuffer(raw,dtype='>i2',count=struct.unpack_from('>H',raw,0x48)[0]*6,offset=u(0x54)+8).reshape(-1,6)
            actual=np.flatnonzero(np.any(points!=0,axis=1));cursor=0
            for j in range(raw[0x4e]):
                a,b,c,width,n,ptr=struct.unpack_from('>4H2I',raw,u(0x5c)+8+j*20)
                codes=np.frombuffer(raw,dtype='>u2',count=n*2,offset=ptr+8).reshape(-1,2)/4096 if width>1 else np.zeros((n,2))
                names=tuple(header['bones'][i]['name']for i in (a,b,c)[:width])
                for i,code in zip(actual[cursor:cursor+n],codes):records.append((bundle,sid,points[i,:3].tobytes(),names,tuple(code)))
                cursor+=n
            if cursor!=len(actual):raise ValueError('Skin/padding enumeration mismatch')
    same=defaultdict(list)
    for i,r in enumerate(records):same[r[2]].append(i)
    pairs=[(x,y)for rows in same.values()for x,y in itertools.combinations(rows,2)
        if records[x][:2]!=records[y][:2]and records[x][3:]!=records[y][3:]and (len(records[x][3])==3 or len(records[y][3])==3)]
    results=[]
    for flip,form,swap,perm in itertools.product((False,True),('a_rest_b','a_b_rest'),(False,True),itertools.permutations(range(3))):
        weights=[]
        for r in records:
            aa,bb=r[4];a,b=(bb,aa)if swap else(aa,bb)
            values=[a,(1-a)*b,(1-a)*(1-b)]if form=='a_rest_b'else[a*(1-b),(1-a)*(1-b),b]
            w=[1.]if len(r[3])==1 else [1-aa,aa]if len(r[3])==2 and flip else [aa,1-aa]if len(r[3])==2 else[values[k]for k in perm]
            weights.append(dict(zip(r[3],w)))
        errors=[max(abs(weights[x].get(k,0)-weights[y].get(k,0))for k in set(weights[x])|set(weights[y]))for x,y in pairs]
        results.append(dict(agreements_below_001=int(sum(e<.001 for e in errors)),mean_maximum_coefficient_delta=float(np.mean(errors)),
            reverse_two_bone=flip,form=form,swap_coefficients=swap,permutation=perm))
    results.sort(key=lambda r:(-r['agreements_below_001'],r['mean_maximum_coefficient_delta']))
    return dict(source_sha256=digest(data),different_palette_or_code_pairs=len(pairs),
        pair_widths={str(k):v for k,v in Counter((len(records[x][3]),len(records[y][3]))for x,y in pairs).items()},
        best_hypotheses=results[:12],source_weight_interpretation='INFERRED, not source-runtime validated',
        do_not_weld=True,flat_three_bone_negative_remainders=int(sum(len(r[3])==3 and sum(r[4])>1 for r in records)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=investigate(a.source.read_bytes())
    with a.out.open('x')as f:json.dump(result,f,indent=2)
