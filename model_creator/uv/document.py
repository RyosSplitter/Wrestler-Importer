"""Native-record UV islands, region filters, reversible edits and portable recipes."""
import base64
import copy
import hashlib
import math
import struct

import numpy as np

from model_creator.morph.document import signature

SCHEMA='psp-model-creator.uv/1'
PAIR_SCHEMA='psp-model-creator/3'
LIBRARY_SCHEMA='psp-model-creator.library-project/3'
REGIONS=('All','Face / head','Torso','Arms','Legs')


def fingerprint(raw):return hashlib.sha256(raw).hexdigest()


def validate_recipe(recipe):
    if recipe is None:return None
    if not isinstance(recipe,dict) or set(recipe)!={'schema','baseline_sha256','edits','textures'} or recipe['schema']!=SCHEMA:
        raise ValueError('Unsupported UV recipe')
    sha=recipe['baseline_sha256']
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid UV baseline fingerprint')
    if not isinstance(recipe['edits'],list) or len(recipe['edits'])>1000000:raise ValueError('Invalid UV edit list')
    seen=set()
    for row in recipe['edits']:
        if not isinstance(row,list) or len(row)!=3 or type(row[0]) is not int or row[0]<0 or row[0] in seen:raise ValueError('Invalid or duplicate UV record')
        if any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1024 for x in row[1:]):raise ValueError('Invalid UV coordinate (supported range -1024 to 1024)')
        seen.add(row[0])
    if not isinstance(recipe['textures'],dict) or len(recipe['textures'])>256:raise ValueError('Invalid UV textures')
    for name,row in recipe['textures'].items():
        if not isinstance(name,str) or not isinstance(row,dict) or set(row)!={'original_sha256','gim'}:raise ValueError('Invalid UV texture binding')
        if not isinstance(row['gim'],str) or len(row['gim'])>8*1024*1024:raise ValueError('UV texture is too large')
        if not isinstance(row['original_sha256'],str) or len(row['original_sha256'])!=64:raise ValueError('Invalid UV texture fingerprint')
        try:base64.b64decode(row['gim'],validate=True)
        except Exception as exc:raise ValueError('Invalid encoded UV texture') from exc
    return copy.deepcopy(recipe)


def attach(project,recipe):
    project=copy.deepcopy(project);recipe=validate_recipe(recipe)
    if recipe and (recipe['edits'] or recipe['textures']):project['uv']=recipe
    else:project.pop('uv',None)
    prefix='psp-model-creator.library-project/' if '.library-project/' in project['schema'] else 'psp-model-creator/'
    project['schema']=prefix+('3' if project.get('uv') else '2' if project.get('morph') else '1')
    return project


def region_labels(model):
    """Bone influence names first; geometry fallback for root-weighted records."""
    from tools.prepare_model import bone_matrices
    points=np.array([v['position'] for mesh in model['meshes'] for v in mesh['vertices']])
    height=float(np.ptp(points[:,1]));low=float(points[:,1].min());matrices=bone_matrices(model)
    anchors={b['name']:matrices[b['index']][:3,3] for b in model['bones']}
    neck=float(anchors.get('kubi',[0,low+height*.19,0])[1]);waist=float(anchors.get('koshi',[0,low+height*.48,0])[1])
    if waist-neck<height*.1:neck=low+height*.19;waist=low+height*.48
    arm_x=max(height*.17,abs(float(anchors.get('l_ninoude',[height*.17,0,0])[0])))
    labels=[]
    def bone_region(name):
        if name.startswith(('atama','d_','l_eye','r_eye','l_mabuta','r_mabuta')) or name=='kubi':return 'Face / head'
        if any(t in name for t in ('ninoude','kote','sakotsu','_te')):return 'Arms'
        if any(t in name for t in ('momo','sune','ashi')):return 'Legs'
        if name in ('mune','koshi'):return 'Torso'
        return None
    for mesh in model['meshes']:
        for v in mesh['vertices']:
            scores={r:0. for r in REGIONS[1:]}
            for bone,w in zip(mesh['bone_palette'],v['weights']):
                r=bone_region(model['bones'][bone]['name'])
                if r:scores[r]+=w
            x,y,_=v['position']
            fallback='Face / head' if y<neck else 'Legs' if y>waist else 'Arms' if abs(x)>arm_x else 'Torso'
            labels.append(max(scores,key=scores.get) if max(scores.values())>.2 else fallback)
    return labels


class Document:
    def __init__(self,raw,textures):
        from model_creator.native import audit_yobj
        self.raw=bytes(raw);self.sha256=fingerprint(raw);self.baseline=audit_yobj(raw)
        self.original_textures=dict(textures);self.textures=dict(textures)
        self.uv=np.array([v['uv'] for m in self.baseline['meshes'] for v in m['vertices']],dtype=np.float32)
        if not np.isfinite(self.uv).all() or np.max(np.abs(self.uv))>1024:raise ValueError('Unsupported UV coordinate range')
        self.original=self.uv.copy();self.selection=set();self.undo_stack=[];self.redo_stack=[]
        self.faces=[];self.texture_ids=[];offset=0
        for mesh in self.baseline['meshes']:
            for mat in mesh['materials']:
                for tri in mat['triangles']:self.faces.append([offset+i for i in tri]);self.texture_ids.append(mat['texture_id'])
            offset+=len(mesh['vertices'])
        self.faces=np.asarray(self.faces,dtype=int);self.texture_ids=np.array(self.texture_ids)
        labels=region_labels(self.baseline)
        self.regions=[max(REGIONS[1:],key=lambda r:sum(labels[i]==r for i in t)) for t in self.faces]
        self.islands=self._islands();self.face_island={f:i for i,fs in enumerate(self.islands) for f in fs}

    def _islands(self):
        # Connect complete continuous geometric/UV edges, including palette-split
        # aliases. Mere overlapping UV coordinates never join unrelated surfaces.
        points=[tuple(v['position'])+tuple(v['uv']) for m in self.baseline['meshes'] for v in m['vertices']]
        parents=list(range(len(self.faces)));edges={}
        def root(i):
            while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
            return i
        for fi,(tri,texture) in enumerate(zip(self.faces,self.texture_ids)):
            for a,b in zip(tri,np.roll(tri,-1)):
                if points[a][:3]==points[b][:3]:continue
                key=(int(texture),tuple(sorted((points[a],points[b]))))
                if key in edges:parents[root(fi)]=root(edges[key])
                else:edges[key]=fi
        groups={}
        for i in range(len(self.faces)):groups.setdefault(root(i),[]).append(i)
        return list(groups.values())

    def visible_faces(self,texture,region='All'):
        return [i for i,t in enumerate(self.texture_ids) if t==texture and (region=='All' or self.regions[i]==region)]

    def vertices(self,faces):return {int(v) for i in faces for v in self.faces[i]}

    def select_island(self,face,visible,add=False,toggle=False):
        ids=self.vertices(set(self.islands[self.face_island[face]])&set(visible))
        if not add:self.selection=set()
        if toggle and ids<=self.selection:self.selection-=ids
        else:self.selection|=ids

    def state(self):return self.uv.copy(),self.textures.copy()

    def remember(self,state=None):
        self.undo_stack.append(self.state() if state is None else state);self.undo_stack=self.undo_stack[-50:];self.redo_stack=[]

    def undo(self,redo=False):
        stack=self.redo_stack if redo else self.undo_stack;other=self.undo_stack if redo else self.redo_stack
        if not stack:return False
        other.append(self.state());self.uv,self.textures=stack.pop();return True

    def transform(self,*,move=(0,0),scale=(1,1),degrees=0,flip=None,history=True,baseline=None):
        if not self.selection:return
        values=np.array([*move,*scale,degrees],float)
        if not np.isfinite(values).all() or any(abs(s)<1e-6 for s in scale):raise ValueError('Use finite transforms and nonzero scale')
        source=self.uv if baseline is None else baseline;ids=sorted(self.selection);p=source[ids].astype(float);center=p.mean(0)
        angle=math.radians(degrees);rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        factors=np.array(scale)*([-1,1] if flip=='U' else [1,-1] if flip=='V' else [1,1])
        result=((p-center)*factors)@rotation.T+center+move
        if not np.isfinite(result).all() or np.max(np.abs(result))>1024:raise ValueError('UV transform exceeds the supported coordinate range')
        result=result.astype(np.float32)
        if np.array_equal(result,self.uv[ids]):return
        if history:self.remember()
        self.uv[ids]=result

    def reset(self,selection=False):
        ids=sorted(self.selection) if selection else list(range(len(self.uv)))
        if np.array_equal(self.uv[ids],self.original[ids]) and (selection or self.textures==self.original_textures):return
        self.remember();self.uv[ids]=self.original[ids]
        if not selection:self.textures=self.original_textures.copy()

    def import_texture(self,name,image):
        from desktop.retexture import encode_edit
        # Show the actual indexed PSP colors, never an unexportable source PNG.
        raw,proof=encode_edit(self.original_textures[name],image)
        if self.textures[name]!=raw:self.remember();self.textures[name]=raw
        return proof

    def recipe(self):
        ids=np.flatnonzero(np.any(self.uv!=self.original,axis=1))
        textures={n:dict(original_sha256=fingerprint(self.original_textures[n]),gim=base64.b64encode(raw).decode('ascii'))
                  for n,raw in self.textures.items() if raw!=self.original_textures[n]}
        if not len(ids) and not textures:return None
        return dict(schema=SCHEMA,baseline_sha256=self.sha256,edits=[[int(i),*map(float,self.uv[i])] for i in ids],textures=textures)

    def restore(self,recipe):
        from desktop.texture_optimizer.candidates import read_gim
        recipe=validate_recipe(recipe)
        if recipe['baseline_sha256']!=self.sha256:raise ValueError('UV baseline changed; reload the original donor selection to recover its UV edits')
        uv=self.original.copy();textures=self.original_textures.copy()
        for i,u,v in recipe['edits']:
            if i>=len(uv):raise ValueError('UV record is outside the native model')
            uv[i]=(u,v)
        for n,row in recipe['textures'].items():
            if n not in textures or fingerprint(textures[n])!=row['original_sha256']:raise ValueError('UV texture baseline changed')
            raw=base64.b64decode(row['gim']);oi,oc=read_gim(textures[n]);ni,nc=read_gim(raw)
            palette_header=48+struct.unpack_from('<I',textures[n],52)[0]
            if len(raw)!=len(textures[n]) or raw[:128]!=textures[n][:128] or raw[palette_header:palette_header+80]!=textures[n][palette_header:palette_header+80] or ni.shape!=oi.shape or not np.array_equal(nc[ni][:,:,3],oc[oi][:,:,3]):
                raise ValueError('UV texture must preserve native dimensions, format, allocation and alpha')
            textures[n]=raw
        self.uv=uv;self.textures=textures

    def model(self,model=None,uv=None,*,texture=None,region='All',isolate=False):
        result=copy.deepcopy(self.baseline if model is None else model);values=self.uv if uv is None else uv;offset=0;face=0
        if sum(len(m['vertices']) for m in result['meshes'])!=len(values):raise ValueError('UV preview topology changed')
        for mesh in result['meshes']:
            for i,v in enumerate(mesh['vertices']):v['uv']=values[offset+i].tolist()
            for mat in mesh['materials']:
                triangles=[]
                for tri in mat['triangles']:
                    if not isolate or ((texture is None or mat['texture_id']==texture) and (region=='All' or self.regions[face]==region)):triangles.append(tri)
                    face+=1
                mat['triangles']=triangles
            offset+=len(mesh['vertices'])
        return result

    def distortion(self,model=None,*,uv=None):
        model=self.baseline if model is None else model
        p=np.array([v['position'] for m in model['meshes'] for v in m['vertices']])[self.faces];t=(self.uv if uv is None else uv)[self.faces]
        area=np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)
        a=t[:,1]-t[:,0];b=t[:,2]-t[:,0];signed=a[:,0]*b[:,1]-a[:,1]*b[:,0]
        ratio=np.abs(signed)/np.maximum(area,1e-20);valid=(area>1e-12)&(ratio>1e-12)
        stretch=np.full(len(area),np.inf)
        for tid in set(self.texture_ids):
            group=valid&(self.texture_ids==tid)
            if group.any():stretch[group]=np.log2(ratio[group]/np.median(ratio[group]))
        original=self.original[self.faces];a=original[:,1]-original[:,0];b=original[:,2]-original[:,0]
        flipped=signed*(a[:,0]*b[:,1]-a[:,1]*b[:,0])<0
        return stretch,flipped
