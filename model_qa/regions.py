"""Bone-anchored anatomical ROIs shared by reference, candidate and all stages."""
from dataclasses import dataclass
import numpy as np
from tools.prepare_model import bone_matrices
from .geometry import AXES


@dataclass
class Region:
    name: str
    lower: np.ndarray
    upper: np.ndarray
    views: tuple

    def mask(self, points):
        return np.all((points >= self.lower)&(points <= self.upper), axis=1)

    def describe(self):
        return dict(lower=self.lower.tolist(), upper=self.upper.tolist(), views=list(self.views),
                    definition='Fixed reference-space ROI from shared PSP bones and original HCTP extents')


def regions(reference, target):
    bm = bone_matrices(target)
    b = {bone['name']: bm[bone['index']][:3, 3]@AXES for bone in target['bones']}
    required = ('atama','kubi','d_kuchi','koshi','mune','l_te','r_te','l_ashi','r_ashi','l_momo','r_momo')
    missing = set(required)-set(b)
    if missing:
        raise ValueError('Missing anatomical anchors: '+','.join(sorted(missing)))
    h = reference.height; p = reference.vertices
    head = p[(p[:,1] > b['kubi'][1])&(np.abs(p[:,0]-b['atama'][0]) < .09*h)]
    if len(head) < 10:
        raise ValueError('Cannot identify the original head extent')
    width = float(np.quantile(np.abs(head[:,0]-b['atama'][0]), .98))
    head_top = float(head[:,1].max()); x = b['atama'][0]
    front = b['atama'][2]+.008*h
    mouth = b['d_kuchi'][1]; neck = b['kubi'][1]
    eye = np.mean([b[n] for n in ('l_eye','r_eye') if n in b], axis=0) if 'l_eye' in b else np.array([x, head_top-.065*h, front])
    out = {}
    def add(name, lo, hi, views=('front','back','left','right')):
        out[name] = Region(name,np.array(lo,dtype=float),np.array(hi,dtype=float),views)
    # The face ROI starts in front of the skull and cannot cover the rear scalp.
    # Reference-only bounds keep the entire skull in the comparison, without
    # rescaling the candidate to hide defects. Escaped vertices also need the
    # bind-selected maximum-error check in model_qa.head.
    add('head',head.min(0)-.005*h,head.max(0)+.005*h,
        ('front','back','left','right','front-left','front-right','back-left','back-right'))
    add('face',[x-width,neck,front],[x+width,head_top, .2*h],('front','left','right','front-left','front-right'))
    add('jaw',[x-width,neck-.012*h,front],[x+width,mouth+.019*h,.2*h],('front','left','right','front-left','front-right'))
    add('chin',[x-.6*width,neck,front],[x+.6*width,mouth-.006*h,.2*h],('front','left','right'))
    add('nose',[x-.38*width,mouth-.003*h,front],[x+.38*width,eye[1],.2*h],('front','left','right'))
    add('eyes',[x-.8*width,eye[1]-.026*h,front],[x+.8*width,eye[1]+.015*h,.2*h],('front','left','right'))
    add('neck',[x-1.15*width,neck-.04*h,-.08*h],[x+1.15*width,neck+.025*h,.1*h],('front','back','left'))
    hip_y=float(np.mean([b['l_momo'][1],b['r_momo'][1]])); waist=b['koshi'][1]; chest=b['mune'][1]
    hip_w=float(abs(b['l_momo'][0]-b['r_momo'][0])*.5+.06*h)
    add('torso',[-hip_w,waist-.01*h,-.13*h],[hip_w,neck-.025*h,.13*h])
    add('waist',[-hip_w,waist-.05*h,-.13*h],[hip_w,waist+.045*h,.13*h])
    add('pelvis',[-hip_w,hip_y-.065*h,-.13*h],[hip_w,waist+.02*h,.13*h])
    add('buttocks',[-hip_w,hip_y-.065*h,-.13*h],[hip_w,waist+.02*h,-.012*h],('back','left','right','back-left','back-right'))
    add('shoulders',[-.21*h,chest+.055*h,-.1*h],[.21*h,neck-.012*h,.1*h],('front','back','front-left'))
    for side in ('left','right'):
        prefix='l_' if side=='left' else 'r_'
        for part, bone, half in [('hands',prefix+'te', [.12*h,.045*h,.075*h]),('feet',prefix+'ashi',[.065*h,.04*h,.14*h])]:
            c=b[bone];delta=np.array(half)
            add(side+'-'+part,c-delta,c+delta,('front','back',side))
    return out
