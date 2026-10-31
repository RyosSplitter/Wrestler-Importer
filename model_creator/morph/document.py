"""Immutable native baseline, parameter history, portable versioned recipes."""
import copy
import hashlib
import json

import numpy as np

from .deform import CONTROLS,ENGINE,active,evaluate,parameters

SCHEMA='psp-model-creator.morph/1'
PAIR_SCHEMA='psp-model-creator/2'
LIBRARY_SCHEMA='psp-model-creator.library-project/2'


def signature(recipe):
    return hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_recipe(recipe):
    if recipe is None:return None
    if not isinstance(recipe,dict) or set(recipe)!={'schema','engine','baseline_sha256','parameters'}:
        raise ValueError('Invalid morph recipe')
    if recipe['schema']!=SCHEMA or recipe['engine']!=ENGINE:raise ValueError('Unsupported morph recipe version')
    value=recipe['baseline_sha256']
    if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Invalid morph baseline fingerprint')
    return dict(recipe,parameters=parameters(recipe['parameters']))


def attach(project,recipe):
    project=copy.deepcopy(project);recipe=validate_recipe(recipe)
    if recipe and active(recipe['parameters']):
        project['schema']=LIBRARY_SCHEMA if '.library-project/' in project['schema'] else PAIR_SCHEMA
        project['morph']=recipe
    else:
        project['schema']='psp-model-creator.library-project/1' if '.library-project/' in project['schema'] else 'psp-model-creator/1'
        project.pop('morph',None)
    if project.get('uv'):
        project['schema']='psp-model-creator.library-project/3' if '.library-project/' in project['schema'] else 'psp-model-creator/3'
    return project


class Document:
    def __init__(self,raw):
        from model_creator.native import audit_yobj
        from tools.prepare_model import bone_matrices
        self.raw=bytes(raw);self.sha256=hashlib.sha256(raw).hexdigest();self.baseline=audit_yobj(raw)
        m=self.baseline;matrices=bone_matrices(m)
        self.anchors={b['name']:matrices[b['index']][:3,3].tolist() for b in m['bones']}
        required={'koshi','mune','kubi'}|{s+n for s in ('l_','r_') for n in ('ninoude','kote','momo','sune','ashi')}
        if not required<=set(self.anchors):raise ValueError('Morph Studio requires verified torso and limb anchors')
        self.points=np.array([v['position'] for mesh in m['meshes'] for v in mesh['vertices']])
        self.normals=np.array([v['normal'] for mesh in m['meshes'] for v in mesh['vertices']])
        self.height=float(np.ptp(self.points[:,1]))
        if self.height<=0 or np.linalg.norm(np.array(self.anchors['mune'])-self.anchors['kubi'])<self.height*.01:
            raise ValueError('This donor has no usable body anchor spacing')
        self.faces=[];offset=0
        for mesh in m['meshes']:
            for mat in mesh['materials']:self.faces.extend([[offset+i for i in tri] for tri in mat['triangles']])
            offset+=len(mesh['vertices'])
        self.faces=np.asarray(self.faces,dtype=int);self.values=parameters();self.undo_stack=[];self.redo_stack=[]

    def set(self,values,*,history=True):
        values=parameters(values)
        if values==self.values:return
        if history:self.undo_stack.append(self.values.copy());self.undo_stack=self.undo_stack[-100:];self.redo_stack=[]
        self.values=values

    def undo(self,redo=False):
        stack=self.redo_stack if redo else self.undo_stack;other=self.undo_stack if redo else self.redo_stack
        if not stack:return False
        other.append(self.values.copy());self.values=stack.pop();return True

    def recipe(self,values=None):
        return dict(schema=SCHEMA,engine=ENGINE,baseline_sha256=self.sha256,parameters=parameters(self.values if values is None else values))

    def restore(self,recipe):
        recipe=validate_recipe(recipe)
        if recipe['baseline_sha256']!=self.sha256:raise ValueError('Morph baseline changed; old vertex edits cannot be applied to this selection')
        self.set(recipe['parameters'],history=False)

    def evaluate(self,values=None):
        p,n=evaluate(self.points,self.normals,self.anchors,self.height,self.values if values is None else values)
        self.check_geometry(p)
        return p,n

    def check_geometry(self,p):
        a=self.points[self.faces];b=np.asarray(p)[self.faces]
        na=np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0]);nb=np.cross(b[:,1]-b[:,0],b[:,2]-b[:,0])
        aa=np.linalg.norm(na,axis=1);bb=np.linalg.norm(nb,axis=1);valid=aa>self.height**2*1e-12
        if np.any(bb[valid]<aa[valid]*.1) or np.any(np.einsum('ij,ij->i',na[valid],nb[valid])<=0):
            raise ValueError('Morph collapses or reverses a source face; reduce the controls')

    def model(self,values=None):
        p,n=self.evaluate(values);m=copy.deepcopy(self.baseline);index=0
        for mesh in m['meshes']:
            for v in mesh['vertices']:v['position']=p[index].tolist();v['normal']=n[index].tolist();index+=1
        return m
