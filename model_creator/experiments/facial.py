"""Topology-led native PSP facial partition research, not a production cutter.

Material names are candidate hints, not semantic guarantees. A depth seed selects
whole native triangles; boundary edges come from their actual topology. Position
clustering below is ONLY an analysis graph: distinct native UV/normal/weight
records are never welded. Ambiguous/nonmanifold contours must be rejected.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import numpy as np

from tools.prepare_model import bone_matrices


@dataclass
class Partition:
    face: set
    attachments: set
    contour: list
    report: dict


def triangles(model):
    for mesh in model['meshes']:
        for mi, mat in enumerate(mesh['materials']):
            name = model['texture_names'][mat['texture_id']]
            for ti, ids in enumerate(mat['triangles']):
                yield (mesh['index'], mi, ti), mesh, mat, ids, name


def point_key(p):
    # Native float roundoff only. Attribute identity remains source mesh+vertex.
    return tuple(np.round(p, 5))


def partition(model, depth=None, *, excluded=frozenset()):
    names = {b['name']: b['index'] for b in model['bones']}
    if not {'atama', 'l_eye', 'r_eye'} <= names.keys():
        raise ValueError('Missing verified head/eye landmarks; manual profile required.')
    world = bone_matrices(model)
    head = world[names['atama'], :3, 3]
    eyes = np.mean([world[names[n], :3, 3] for n in ('l_eye', 'r_eye')], axis=0)
    depth = float((head[2]+eyes[2])*.5 if depth is None else depth)
    candidates, selected, attachments = [], set(), set()
    positions, directed, all_edges = {}, {}, defaultdict(list)
    for key, mesh, mat, ids, texture in triangles(model):
        p = np.array([mesh['vertices'][i]['position'] for i in ids])
        if 'face' in texture.casefold():
            candidates.append(key)
            if p[:, 2].mean() < depth and key not in excluded:
                selected.add(key)
                ks = [point_key(v) for v in p]
                for k, v in zip(ks, p):positions.setdefault(k, v)
                for a, b in zip(ks, ks[1:]+ks[:1]):
                    edge = tuple(sorted((a, b)))
                    all_edges[edge].append(key);directed[edge] = (a, b)
        elif ((texture.casefold().endswith(('_eye', '_ha', '_eyelash'))
               or texture.casefold() in ('blood', 'bandage'))
              and p[:, 1].max() < -6.8):
            attachments.add(key)
    if not selected:raise ValueError('No facial skin identified; explicit material profile required.')
    bad = [e for e, fs in all_edges.items() if len(fs)>2]
    boundary = [directed[e] for e, fs in all_edges.items() if len(fs)==1]
    adjacency = defaultdict(set)
    for a, b in boundary:adjacency[a].add(b);adjacency[b].add(a)
    if bad or any(len(v)!=2 for v in adjacency.values()):
        raise ValueError('Facial boundary is ambiguous/nonmanifold; refusing automatic cut.')
    loops, unvisited = [], set(adjacency)
    while unvisited:
        start = min(unvisited);loop = [start];previous = None;current = start
        while True:
            choices = sorted(adjacency[current]-({previous} if previous is not None else set()))
            nxt = choices[0]
            if nxt==start:break
            if nxt in loop:raise ValueError('Self-touching facial boundary.')
            loop.append(nxt);previous,current=current,nxt
        unvisited.difference_update(loop);loops.append(loop)
    # Eye/mouth openings are native intentional loops. The outer contour has
    # greatest projected XY area; smaller loops stay untouched inside the insert.
    area = lambda loop: abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(loop,loop[1:]+loop[:1])))*.5
    loops.sort(key=area, reverse=True)
    contour = loops[0]
    projected_area = area(contour)
    if projected_area<.1:raise ValueError('No meaningful outer facial contour.')
    # Record both donor-native records on either side of shared geometric edges.
    selected_edges = {tuple(sorted((a,b))) for a,b in zip(contour,contour[1:]+contour[:1])}
    shared = set()
    for key, mesh, mat, ids, texture in triangles(model):
        if key in selected or key in attachments:continue
        ks=[point_key(mesh['vertices'][i]['position']) for i in ids]
        shared.update(tuple(sorted((a,b))) for a,b in zip(ks,ks[1:]+ks[:1]) if tuple(sorted((a,b))) in selected_edges)
    if shared!=selected_edges:
        raise ValueError('Outer facial edge is not paired with head shell; cut needs manual review.')
    face_meshes=sorted({k[0] for k in selected})
    materials=sorted({model['texture_names'][model['meshes'][i]['materials'][j]['texture_id']] for i,j,_ in selected})
    return Partition(selected, attachments, [positions[k] for k in contour], dict(
        classification='INFERRED material-name hints plus head/eye landmark depth seed; topology-checked boundary',
        face_triangles=len(selected), attachment_triangles=len(attachments),
        candidate_skin_triangles=len(candidates), face_meshes=face_meshes,
        face_textures=materials, contour_vertices=len(contour),
        interior_openings=[len(l) for l in loops[1:]], projected_outer_area=projected_area,
        depth_seed=depth, existing_triangle_edges_only=True,
        shell_boundary_edges_verified=len(shared), topology_correspondence_assumed=False,
        position_clustering_tolerance=1e-5, native_attribute_records_welded=False))


def inventory(model):
    """Report native material topology without requiring successful extraction."""
    rows=[]
    for mesh in model['meshes']:
        for mi, mat in enumerate(mesh['materials']):
            name=model['texture_names'][mat['texture_id']]
            if 'face' not in name.casefold():continue
            ids=sorted({i for t in mat['triangles'] for i in t})
            used=Counter()
            for i in ids:
                for b,w in zip(mesh['bone_palette'],mesh['vertices'][i]['weights']):
                    if w>0:used[model['bones'][b]['name']]+=1
            rows.append(dict(mesh=mesh['index'],material=mi,texture=name,
                vertices=len(ids),triangles=len(mat['triangles']),
                uv_bounds=[np.min([mesh['vertices'][i]['uv'] for i in ids],axis=0).tolist(),
                           np.max([mesh['vertices'][i]['uv'] for i in ids],axis=0).tolist()],
                stride=mesh['stride'],palette=[model['bones'][b]['name'] for b in mesh['bone_palette']],
                nonzero_influence_records=dict(used)))
    return rows


def regularized_partition(model,depth=None):
    """Remove outer topological ears from the insert, retaining them in shell.

    An ear has all three corners on the outer attachment and two outer edges.
    Mapping such a cap to another donor's nonplanar/indented contour can invert
    it even while both rings close. Keep these triangles in their ORIGINAL shell
    instead. This changes partition ownership, never their native geometry.
    Bounded removal protects against eroding the actual facial feature region.
    """
    excluded=set();initial=partition(model,depth);part=initial
    for iteration in range(5):
        ring={point_key(p) for p in part.contour}
        edges={tuple(sorted((point_key(a),point_key(b)))) for a,b in zip(part.contour,part.contour[1:]+part.contour[:1])}
        ears=set()
        for key,mesh,mat,ids,texture in triangles(model):
            if key not in part.face:continue
            ks=[point_key(mesh['vertices'][i]['position']) for i in ids]
            if set(ks)<=ring and sum(tuple(sorted((a,b))) in edges for a,b in zip(ks,ks[1:]+ks[:1]))>=2:ears.add(key)
        if not ears:
            part.report['outer_ear_triangles_retained_in_shell']=[list(k) for k in sorted(excluded)]
            part.report['outer_ear_policy']='Topology-only boundary regularization; source triangles retained unchanged in shell'
            return part
        excluded|=ears
        if len(excluded)>initial.report['face_triangles']*.1:raise ValueError('Boundary regularization would remove too much face; manual profile required.')
        part=partition(model,depth,excluded=excluded)
    raise ValueError('Boundary regularization did not converge within five passes.')


def records(model, source, names, keep, translation=None):
    """Keep record identity through partitioning; never weld by position."""
    translation=np.zeros(3) if translation is None else np.asarray(translation)
    remap=[names.index(b['name']) for b in model['bones']]
    result=[]
    for key,mesh,mat,ids,texture in triangles(model):
        if not keep(key):continue
        poly=[]
        for i in ids:
            v=mesh['vertices'][i];w=np.zeros(len(names));w[np.array(remap)[mesh['bone_palette']]]=v['weights']
            poly.append(dict(p=np.asarray(v['position'])+translation,n=np.asarray(v['normal']),
                uv=np.asarray(v['uv']),c=np.asarray(v['color'],float),w=w,
                origin=(source,mesh['index'],i),changed=False))
        result.append(dict(source=source,mesh=key[0],material=key[1],triangle=key[2],poly=poly))
    return result


def lerp(a,b,t):
    result={k:(1-t)*a[k]+t*b[k] for k in ('p','n','uv','c','w')}
    result.update(origin=None,changed=True)
    return result


class Contour:
    """Nonplanar contour with checked one-to-one polar parameterization in XY."""
    def __init__(self, partition, rows, translation=None):
        delta=np.zeros(3) if translation is None else np.asarray(translation)
        self.points=np.array(partition.contour)+delta
        self.keys=[point_key(p) for p in self.points]
        self.center=(self.points[:,:2].min(0)+self.points[:,:2].max(0))*.5
        angles=np.array([self.angle(p) for p in self.points])
        steps=(np.roll(angles,-1)-angles+np.pi)%(2*np.pi)-np.pi
        if not (np.all(steps>1e-6) or np.all(steps < -1e-6)):
            raise ValueError('Projected outer face contour folds; choose a different topology-checked depth seed.')
        if steps.mean()<0:
            self.points=self.points[::-1];self.keys=self.keys[::-1];angles=angles[::-1]
        self.angles=angles
        self.edge_keys={tuple(sorted((a,b))) for a,b in zip(self.keys,self.keys[1:]+self.keys[:1])}
        self.attributes={}
        for row in rows:
            for v in row['poly']:
                key=point_key(v['p'])
                if key in self.keys:
                    if key in self.attributes:
                        old=self.attributes[key]
                        if np.max(np.abs(old['w']-v['w']))>2e-6:
                            raise ValueError('Legitimate incompatible source weights on attachment contour; manual seam profile required.')
                    else:self.attributes[key]=v
        if set(self.attributes)!=set(self.keys):raise ValueError('Missing source contour attributes.')

    def angle(self,p):return float(np.arctan2(p[1]-self.center[1],p[0]-self.center[0])%(2*np.pi))

    def locate(self,angle):
        for i,a in enumerate(self.angles):
            b=self.angles[(i+1)%len(self.points)];span=(b-a)%(2*np.pi);offset=(angle-a)%(2*np.pi)
            if offset<=span+1e-8:
                p,q=self.points[i],self.points[(i+1)%len(self.points)]
                ray=np.array([np.cos(angle),np.sin(angle)])
                matrix=np.column_stack((ray,-(q-p)[:2]))
                _,t=np.linalg.solve(matrix,p[:2]-self.center)
                return i,float(np.clip(t,0,1))
        raise ValueError('Contour parameter has no valid edge.')

    def sample(self,angle):
        i,t=self.locate(angle)
        return lerp(self.attributes[self.keys[i]],self.attributes[self.keys[(i+1)%len(self.keys)]],t)


def stitch_contours(shell_rows, insert_rows, shell_part, insert_part, translation):
    """Split both real edge chains at their union, then fit insert boundary only.

    Head shell coordinates stay on their original edges. All interior donor
    features keep a single rigid translation. No hidden surface projection,
    nearest-vertex correspondence, position weld, or nonuniform scaling occurs.
    """
    outer=Contour(shell_part,shell_rows);inner=Contour(insert_part,insert_rows,translation)
    angles=sorted(set(round(float(a),11) for c in (outer,inner) for a in c.angles))
    moved=[];added=0
    for contour,rows,is_insert in ((outer,shell_rows,False),(inner,insert_rows,True)):
        for row in rows:
            original=row['poly'];poly=[]
            for v in original:v['boundary']=point_key(v['p']) in contour.keys
            for a,b in zip(original,original[1:]+original[:1]):
                ka,kb=point_key(a['p']),point_key(b['p']);new=[a]
                if tuple(sorted((ka,kb))) in contour.edge_keys:
                    aa,ab=contour.angle(a['p']),contour.angle(b['p'])
                    step=(ab-aa+np.pi)%(2*np.pi)-np.pi
                    pending=[]
                    for angle in angles:
                        f=((angle-aa+np.pi)%(2*np.pi)-np.pi)/step
                        if 1e-7<f<1-1e-7:
                            ray=np.array([np.cos(angle),np.sin(angle)])
                            _,t=np.linalg.solve(np.column_stack((ray,-(b['p']-a['p'])[:2])),a['p'][:2]-contour.center)
                            if 1e-7<t<1-1e-7:pending.append((t,angle))
                    for t,angle in sorted(pending):
                        new.append(dict(lerp(a,b,t),boundary=True));added+=1
                for v in new:
                    # Edge intersections and existing ring corners only.
                    on_ring=(point_key(v['p']) in contour.keys or v['origin'] is None)
                    if is_insert and on_ring:
                        target=outer.sample(contour.angle(v['p']))
                        moved.append(float(np.linalg.norm(v['p']-target['p'])))
                        v=dict(v,p=target['p'],w=target['w'],n=target['n'],changed=True)
                    poly.append(v)
            row['poly']=poly
    return dict(method='Existing edge contour union; rigid donor interior, localized boundary fit',
        angular_samples=len(angles),edge_records_added=added,
        donor_ring_records_fitted=sum(v['changed'] for r in insert_rows for v in r['poly']),
        maximum_boundary_displacement=max(moved,default=0.),
        no_nonuniform_scaling=True,interior_geometry_preserved=True,
        seam_texture_blending=False,
        seam_points=[outer.sample(angle)['p'].tolist() for angle in angles])


def fan(poly):
    # Some native triangles have ALL THREE vertices on a zigzag cut contour.
    # Fitting can straighten one edge. A fixed fan then discards its collinear
    # samples and creates T junctions. Ear clipping keeps EVERY boundary segment.
    if len(poly)==3:return [poly]
    p=np.array([v['p'] for v in poly]);normal=np.cross(p,np.roll(p,-1,axis=0)).sum(0)
    # Entirely boundary-owned caps lie on the fitted nonplanar contour. Its
    # verified one-to-one chart is XY; a normal-based projection can fold in XZ.
    axis=2 if all(v.get('boundary',False) for v in poly) else int(np.argmax(np.abs(normal)))
    xy=np.delete(p,axis,axis=1)
    cross=lambda a,b:float(a[0]*b[1]-a[1]*b[0])
    area=sum(cross(a,b) for a,b in zip(xy,np.roll(xy,-1,axis=0)))
    if abs(area)<1e-12:raise ValueError('Collapsed facial attachment polygon.')
    sign=np.sign(area);order=list(range(len(poly)));result=[]
    while len(order)>3:
        found=False
        for j,b in enumerate(order):
            a,c=order[j-1],order[(j+1)%len(order)]
            if sign*cross(xy[b]-xy[a],xy[c]-xy[a])<=1e-12:continue
            inside=False
            for i in order:
                if i in (a,b,c):continue
                if all(sign*cross(xy[v]-xy[u],xy[i]-xy[u])>=-1e-12 for u,v in ((a,b),(b,c),(c,a))):inside=True;break
            if inside:continue
            result.append([poly[i] for i in (a,b,c)]);order.pop(j);found=True;break
        if not found:raise ValueError('Facial attachment polygon folds or cannot preserve its boundary.')
    result.append([poly[i] for i in order])
    if any(np.linalg.norm(np.cross(t[1]['p']-t[0]['p'],t[2]['p']-t[0]['p']))<=1e-10 for t in result):
        raise ValueError('Degenerate facial attachment triangle.')
    return result


def serialize(base, sources, rows):
    """Use the existing native writer, immutable materials, stable draw order."""
    import copy
    import struct
    from tools.psp_mesh_merge import write_model
    from tools.stripify import stripify,join_strips
    from model_creator.native import audit_yobj
    from desktop.skinning import adapt_yobj
    if any(len(s['model'].get('descriptors',[None]))!=1 for s in sources):
        raise ValueError('First facial prototype supports one descriptor per donor only.')
    names=[b['name'] for b in base['bones']];meshes=[];texture_names=[];textures={};origins=[]
    buckets=[]
    for row in rows:
        for tri in fan(row['poly']):
            active={int(b) for v in tri for b in np.flatnonzero(v['w']>0)}
            if len(active)>8:raise ValueError('Facial seam needs more than eight bone slots.')
            key=(row['source'],row['mesh'],row['material'])
            if not buckets or buckets[-1]['key']!=key or len(buckets[-1]['bones']|active)>8:
                buckets.append(dict(key=key,bones=set(),faces=[]))
            buckets[-1]['bones']|=active;buckets[-1]['faces'].append(tri)
    for bucket in buckets:
        si,mi,ai=bucket['key'];source=sources[si];donor=source['model']['meshes'][mi]
        mat=copy.deepcopy(donor['materials'][ai]);oldname=source['model']['texture_names'][mat['texture_id']]
        if len({h[:8] for h in mat['strip_headers']})!=1:
            raise ValueError('Different opaque strip metadata cannot be restripified safely.')
        texture=source['textures'][oldname.casefold()];texname=oldname
        if texname in textures and textures[texname]!=texture:texname=f'f{si}_{len(texture_names):02d}'
        if texname not in textures:texture_names.append(texname);textures[texname]=texture
        record=bytearray(mat['raw']);struct.pack_into('<H',record,22,texture_names.index(texname))
        mat.update(raw=bytes(record),texture_id=texture_names.index(texname))
        palette=sorted(bucket['bones'])
        # Preserve original zero slots where available; native one-slot rendering
        # adaptation remains the existing audited compatibility rule.
        for b in donor['bone_palette']:
            idx=names.index(source['model']['bones'][b]['name'])
            if idx not in palette and len(palette)<donor['weight_slots']:palette.append(idx)
        vertices=[];indices=[];lookup={}
        for tri in bucket['faces']:
            face=[]
            for v in tri:
                key=(v['origin'],b''.join(np.asarray(v[k],'<f8').tobytes() for k in ('p','n','uv','c','w')))
                if key not in lookup:
                    lookup[key]=len(vertices);normal=v['n']
                    if v['changed']:normal=normal/max(np.linalg.norm(normal),1e-12)
                    vertices.append(dict(position=v['p'].tolist(),normal=normal.tolist(),uv=v['uv'].tolist(),
                        color=np.rint(v['c']).clip(0,255).astype(int).tolist(),weights=v['w'][palette].tolist()))
                    origins.append((len(meshes),len(vertices)-1,v['origin'],v['changed']))
                face.append(lookup[key])
            indices.append(face)
        strips=join_strips(stripify(indices));mat.update(triangles=indices,strips=strips,strip_headers=[mat['strip_headers'][0]]*len(strips))
        mesh=copy.deepcopy(donor);mesh.update(index=len(meshes),vertices=vertices,bone_palette=palette,
            weight_slots=len(palette),stride=36+4*len(palette),materials=[mat])
        mesh['raw_vertices']=b''.join(struct.pack('<'+'f'*len(palette)+'2f4B6f',*v['weights'],*v['uv'],*v['color'],*v['normal'],*v['position']) for v in vertices)
        points=np.array([v['position'] for v in vertices]);center=(points.min(0)+points.max(0))/2
        header=bytearray(mesh['raw_header']);struct.pack_into('<4f',header,48,*center,float(np.linalg.norm(points-center,axis=1).max()+.001));mesh['raw_header']=bytes(header)
        meshes.append(mesh)
    result=copy.deepcopy(base);result.update(meshes=meshes,texture_names=texture_names,
        texture_raw=b''.join(n.encode('ascii').ljust(16,b'\0') for n in texture_names))
    header=bytearray(base['header']);struct.pack_into('<I',header,32,len(texture_names));result['header']=bytes(header)
    if len(base.get('descriptors',[None]))!=1:raise ValueError('First facial prototype supports one descriptor per donor only.')
    reserved_alias=60 in result['report']['relocation_locations']
    if reserved_alias:
        if struct.unpack_from('<I',header,60)[0]!=0:raise ValueError('Unknown header-60 pointer.')
        result['report']['relocation_locations']=[i for i in result['report']['relocation_locations'] if i!=60]
    raw=write_model(result,[[i] for i in range(len(meshes))]);raw,slot_report=adapt_yobj(raw)
    if reserved_alias:
        from tools.psp_mesh_audit import encode_relocations
        from tools.yobj_alignment import align_yobj_pof0
        reloc=encode_relocations(sorted(audit_yobj(raw)['report']['relocation_locations']+[60]))
        end=8+struct.unpack_from('<I',raw,4)[0]
        raw=align_yobj_pof0(raw[:end]+b'POF0'+struct.pack('<I',len(reloc))+reloc)
    model=audit_yobj(raw)
    if len(model['meshes'])!=len(meshes):raise ValueError('Unexpected mesh count after slot adaptation.')
    # Check oriented triangle + attribute multisets independently of new indices.
    expected=[];actual=[]
    def signature(v,bones):
        return (tuple(np.float32(v['position'])),tuple(np.float32(v['normal'])),tuple(np.float32(v['uv'])),
            tuple(v['color']),tuple(sorted((names[b],float(np.float32(w))) for b,w in zip(bones,v['weights']) if w)) )
    for before,after in zip(meshes,model['meshes']):
        for target,array in ((expected,before),(actual,after)):
            for mat in array['materials']:
                for tri in mat['triangles']:
                    vertices=[signature(array['vertices'][i],array['bone_palette']) for i in tri]
                    target.append(min(tuple(vertices[i:]+vertices[:i]) for i in range(3)))
    if Counter(expected)!=Counter(actual):raise ValueError('Facial native serialization altered attributes, weights or winding.')
    return raw,textures,origins,dict(oriented_attribute_triangles_identical=True,slot_compatibility=slot_report)


def graft_rig(shell, insert, shell_rows, insert_rows, translation, shared_fraction=0.):
    """Graft donor expression pivots in world space, keep shell head/body binds.

    A controller still used by retained shell geometry is shared. Its translation
    can only move along the two measured native pivots, with subsequent independent
    donor-expression AND retained-shell pose checks. No weight compensation.
    """
    import copy
    import struct
    from tools.prepare_model import local_matrix
    from tools.weight_trial_review import descendant_names
    base=copy.deepcopy(shell);names=[b['name'] for b in shell['bones']]
    donor_names=[b['name'] for b in insert['bones']]
    if set(names)!=set(donor_names):raise ValueError('First facial prototype requires the same named bone set.')
    facial=descendant_names(shell,'atama')-{'atama'}
    used=lambda rows:{names[i] for r in rows for v in r['poly'] for i in np.flatnonzero(v['w']>0)}
    shell_used=used(shell_rows);insert_used=used(insert_rows)
    sw,dw=bone_matrices(shell),bone_matrices(insert)
    desired={};report=[]
    for name in names:
        i=names.index(name);j=donor_names.index(name)
        parent=lambda m,b:None if b['parent']==-1 else m['bones'][b['parent']]['name']
        if parent(shell,shell['bones'][i])!=parent(insert,insert['bones'][j]):raise ValueError('Different facial hierarchy: '+name)
        value=sw[i].copy()
        if name in facial:
            # Even zero-weight intermediary controllers are necessary ancestors.
            value=dw[j].copy();value[:3,3]+=translation
            if name in shell_used:
                if np.max(np.abs(sw[i,:3,:3]-value[:3,:3]))>2e-5:
                    raise ValueError('Shared controller rotations differ: '+name)
                value[:3,3]=sw[i,:3,3]+shared_fraction*(value[:3,3]-sw[i,:3,3])
            report.append(dict(bone=name,shared=name in shell_used,
                insert_nonzero=name in insert_used,world_translation=value[:3,3].tolist()))
        desired[name]=value
    raw=bytearray(shell['bone_raw'])
    for i,b in enumerate(base['bones']):
        if b['name'] not in facial:continue
        parent=names[b['parent']];local=np.linalg.inv(desired[parent])@desired[b['name']]
        position=local[:3,3]
        # Equivalent Euler decompositions can CHANGE native local animation axes
        # at gimbal lock. Keep the donor's actual rotation record, not as_euler.
        donor_bone=insert['bones'][donor_names.index(b['name'])]
        rotation=donor_bone['rotation']
        if np.max(np.abs(local_matrix(donor_bone)[:3,:3]-local[:3,:3]))>2e-5:
            raise ValueError('Native controller axes incompatible with shell: '+b['name'])
        b.update(local_position=tuple(position),rotation=tuple(rotation))
        struct.pack_into('<3f',raw,i*80+16,*position);struct.pack_into('<3f',raw,i*80+32,*rotation)
    # Conservative native culling sphere union; never shrink observed bounds.
    for i,name in enumerate(names):
        j=donor_names.index(name);a=np.array(struct.unpack_from('<4f',shell['bone_raw'],i*80+64));b=np.array(struct.unpack_from('<4f',insert['bone_raw'],j*80+64))
        radius=max(a[3],float(np.linalg.norm((b[:3]+translation)-a[:3])+b[3]))+1e-5
        struct.pack_into('<f',raw,i*80+76,radius)
    base['bone_raw']=bytes(raw)
    return base,dict(controllers=report,shared_native_pivot_fraction=shared_fraction,
        head_neck_body_bind_unchanged=True,nonuniform_scale=False,
        note='Controller-name semantics remain inferred; analytical tests do not replace game clips.')


def pose_review(output, sources, origins, translation, seam_points=()):
    """Independent source-expression reference in the shared shell head frame."""
    from model_creator.core import POSES,dense
    from model_creator.rigging import deform_local
    from tools.weight_trial_review import deform,skin_matrices
    from tools.prepare_model import local_matrix
    from tools.weight_trial_review import rotation,descendant_names
    p,w=dense(output);offsets=np.cumsum([0]+[len(m['vertices']) for m in output['meshes']])
    names=[b['name'] for b in output['bones']];shell,donor=[dict(s['model'],bone_count=len(s['model']['bones'])) for s in sources]
    output=dict(output,bone_count=len(output['bones']))
    source_dense=[dense(s['model']) for s in sources]
    source_offsets=[np.cumsum([0]+[len(m['vertices']) for m in s['model']['meshes']]) for s in sources]
    # Verify records against sources BEFORE posing. Boundary changes are explicit.
    checks=[];maximum_geometry_error=0.
    for mi,vi,origin,changed in origins:
        if origin is None or changed:continue
        si,sm,sv=origin;v=output['meshes'][mi]['vertices'][vi];old=sources[si]['model']['meshes'][sm]['vertices'][sv]
        error=float(np.linalg.norm(np.asarray(v['position'])-np.asarray(old['position'])-(translation if si else 0)))
        maximum_geometry_error=max(maximum_geometry_error,error)
        if error>2e-6 or max(abs(np.array(v['uv'])-old['uv']))>1e-7:raise ValueError('Untouched facial/source record changed.')
        if v['normal']!=old['normal'] or v['color']!=old['color']:raise ValueError('Untouched source normal/color changed.')
        a={names[b]:float(w) for b,w in zip(output['meshes'][mi]['bone_palette'],v['weights']) if w}
        b={sources[si]['model']['bones'][b]['name']:float(w) for b,w in zip(sources[si]['model']['meshes'][sm]['bone_palette'],old['weights']) if w}
        if a!=b:raise ValueError('Untouched source facial weights changed.')
        checks.append((int(offsets[mi]+vi),si,int(source_offsets[si][sm]+sv)))
    all_poses=dict(POSES,head_turn={'atama':('y',25)},jaw_wide={'d_kuchi':('x',25)},
        blink={'l_mabuta':('x',25),'r_mabuta':('x',25)},
        eye_up={'l_eye':('x',15),'r_eye':('x',15)},
        mouth_corners={'l_kuchi':('z',12),'r_kuchi':('z',-12)})
    facial=descendant_names(donor,'atama')-{'atama'};reports={}
    seam_groups=defaultdict(list);seam_keys={point_key(v) for v in seam_points}
    for i,v in enumerate(p):
        if point_key(v) in seam_keys:seam_groups[point_key(v)].append(i)
    for axis,pose_function in (('model',deform),('local',deform_local)):
        report={}
        for label,controls in all_poses.items():
            out=pose_function(output,p,w,controls)
            if not np.isfinite(out).all():raise ValueError('Nonfinite facial pose '+label)
            expected_shell=pose_function(shell,*source_dense[0],controls)
            expression={k:v for k,v in controls.items() if k in facial}
            expected_donor=pose_function(donor,*source_dense[1],expression)+translation
            if axis=='model':head_motion=skin_matrices(shell,controls)[names.index('atama')]
            else:
                rest=bone_matrices(shell);cache={}
                def world(i):
                    if i not in cache:
                        b=shell['bones'][i];mat=local_matrix(b)
                        if b['name'] in controls:
                            r=np.eye(4);r[:3,:3]=rotation(*controls[b['name']]);mat=mat@r
                        cache[i]=mat if b['parent']==-1 else world(b['parent'])@mat
                    return cache[i]
                i=names.index('atama');head_motion=world(i)@np.linalg.inv(rest[i])
            expected_donor=(np.column_stack((expected_donor,np.ones(len(expected_donor))))@head_motion.T)[:,:3]
            errors=[[],[]]
            for oi,si,sv in checks:errors[si].append(float(np.linalg.norm(out[oi]-(expected_shell if si==0 else expected_donor)[sv])))
            gap=max((float(np.linalg.norm(out[ids]-out[ids[0]],axis=1).max()) for ids in seam_groups.values()),default=0.)
            maximum=max(max(errors[0],default=0.),max(errors[1],default=0.))
            report[label]=dict(retained_shell_max_error=max(errors[0],default=0.),
                donor_core_max_error=max(errors[1],default=0.),seam_gap=gap,
                passed=maximum<=.03 and gap<=3e-4,finite=True)
        reports[axis]=report
    return dict(poses=reports,passed=all(p['passed'] for r in reports.values() for p in r.values()),
        records_verified=len(checks),maximum_static_source_error=maximum_geometry_error,
        source_pose_tolerance=.03,seam_gap_tolerance=3e-4,
        reference='Donor intrinsic expressions rigidly attached in shell head frame; retained shell compared to its own native rig',
        actual_game_clips_tested=False)


def topology_review(model, seam_points):
    """Validate actual serialized ordinary surface around the deliberate join."""
    ring=[point_key(v) for v in seam_points]
    expected={tuple(sorted((a,b))) for a,b in zip(ring,ring[1:]+ring[:1])}
    edges=defaultdict(list);degenerate=[];faces=Counter()
    for key,mesh,mat,ids,texture in triangles(model):
        if texture.casefold() in ('blood','blood_b','bandage'):continue
        p=np.array([mesh['vertices'][i]['position'] for i in ids]);ks=[point_key(v) for v in p]
        if np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))<=1e-10:degenerate.append(key)
        faces[tuple(sorted(ks))]+=1
        for a,b in zip(ks,ks[1:]+ks[:1]):
            edge=tuple(sorted((a,b)))
            if edge in expected:edges[edge].append((a,b))
    failures=[dict(edge=e,uses=len(edges[e]),opposite_winding=len(edges[e])==2 and edges[e][0]==edges[e][1][::-1])
        for e in sorted(expected) if len(edges[e])!=2 or edges[e][0]!=edges[e][1][::-1]]
    return dict(passed=not failures and not degenerate,
        attachment_edges=len(expected),paired_opposite_attachment_edges=len(expected)-len(failures),
        failed_attachment_edges=failures,degenerate_ordinary_triangles=degenerate,
        duplicate_geometric_faces=sum(v-1 for v in faces.values() if v>1),
        global_self_intersections_tested=False,
        limitation='Only the new attachment is required to be manifold. Native eye/mouth openings and distinct attribute seams remain.')


def source_signature(model, textures):
    """Oriented attributes, named nonzero weights, texture bytes and render flags."""
    import hashlib
    result=Counter()
    for key,mesh,mat,ids,texture in triangles(model):
        values=[]
        for i in ids:
            v=mesh['vertices'][i]
            values.append((tuple(v['position']),tuple(v['normal']),tuple(v['uv']),tuple(v['color']),
                tuple(sorted((model['bones'][b]['name'],w) for b,w in zip(mesh['bone_palette'],v['weights']) if w))))
        oriented=min(tuple(values[i:]+values[:i]) for i in range(3))
        # Pointer/count fields are rewritten; material behavior/control retained.
        material=bytearray(mat['raw']);material[22:24]=b'\0'*2;material[132:144]=bytes(12)
        result[(oriented,bytes(material),hashlib.sha256(textures[texture.casefold()]).hexdigest())]+=1
    return result


def winding_review(rows,sources):
    """Do not mistake a closed seam for an acceptable facial surface."""
    inverted=[];minimum=1.;checked=0
    for row in rows:
        m=sources[row['source']]['model']['meshes'][row['mesh']]
        ids=m['materials'][row['material']]['triangles'][row['triangle']]
        p=np.array([m['vertices'][i]['position'] for i in ids])
        normal=np.cross(p[1]-p[0],p[2]-p[0]);length=np.linalg.norm(normal)
        if length<=1e-10:raise ValueError('Degenerate source triangle requires separate review.')
        normal/=length
        for tri in fan(row['poly']):
            n=np.cross(tri[1]['p']-tri[0]['p'],tri[2]['p']-tri[0]['p']);n/=np.linalg.norm(n)
            dot=float(normal@n);minimum=min(minimum,dot);checked+=1
            if dot<=0:inverted.append(dict(source=row['source'],mesh=row['mesh'],material=row['material'],triangle=row['triangle'],normal_dot=dot))
    return dict(passed=not inverted,checked_triangles=checked,minimum_original_normal_dot=minimum,
        opposed_source_faces=inverted,
        caveat='Relative orientation test, not a proof that no global self-intersections exist.')
