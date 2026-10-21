"""Isolated entrance retry: retain more body faces and independent color budgets.

The rejected nearest-source projection is deliberately not called. Production
and the user-accepted ring geometry remain unchanged.
"""
import argparse
from tools.wwe13_wii_trial import run
from tools.wwe13_wii_texture_refine import candidates


def retry(source,base,out):
    return run(source,base,out,index=1,ratio=.35,head_floor=.6,hand_floor=.5,
               mouth_ratio=.6,material_only=True,texture_candidates=candidates)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--base',required=True);p.add_argument('--out',required=True);a=p.parse_args();print(retry(a.source,a.base,a.out))
