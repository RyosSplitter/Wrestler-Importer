"""Independent pad-surface, seam-motion and retained-face regression review."""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from model_qa.geometry import geometry, posed, Surface, distribution
from model_qa.ocular import probes, skin
from model_qa.pipeline import POSES
from model_qa.render import camera, raster
from tools.jericho_elbow_guard_trial import TEXTURE, position, selected
from tools.lance_anatomy_restore import boundary
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections, write_json
from tools.weight_trial_review import descendant_names

PAD_POSES = {
    'rest': {},
    'standing': POSES['standing'],
    'elbow-flex-60': dict(POSES['standing'], r_kote=('y',60)),
    'elbow-flex-110': dict(POSES['standing'], r_kote=('y',110)),
    'forearm-twist': dict(POSES['standing'], r_kote=('x',45)),
    'arms-raised': POSES['shoulders-up'],
}


def pad(g):
    result = copy.copy(g)
    result.faces = g.faces[np.asarray(g.face_textures) == TEXTURE]
    result.face_textures = [TEXTURE] * len(result.faces)
    return result


def evaluate(source, before, after, folder=None, samples=10000):
    ref, old, new = map(geometry, (source, before, after))
    height = ref.height
    metrics, renders = {}, []
    tid = source['textures'].index(TEXTURE)
    boundary_points = {p for e in boundary(source,tid) for p in e}
    seam_groups = []
    for key in sorted(boundary_points):
        ids = [j for j,(mi,vi) in enumerate(new.vertex_records)
               if position(after['meshes'][mi]['vertices'][vi]) == key]
        if len(ids) < 2:
            raise ValueError('Original pad boundary lacks its adjacent skin alias')
        seam_groups.append(ids)
    for name, controls in PAD_POSES.items():
        rr, oo, nn = [posed(g,controls) for g in (ref,old,new)]
        rs, os, ns = [Surface(pad(g),height) for g in (rr,oo,nn)]
        points,_,_ = rs.sample(samples)
        old_dist = os.nearest(points)[1]
        new_dist = ns.nearest(points)[1]
        op,_,_ = os.sample(samples);np_,_,_ = ns.sample(samples)
        old_reverse, new_reverse = rs.nearest(op)[1], rs.nearest(np_)[1]
        seam_gap = max(float(np.linalg.norm(nn.vertices[ids]-nn.vertices[ids[0]],axis=1).max()) for ids in seam_groups)
        metrics[name] = dict(before=distribution(np.r_[old_dist,old_reverse],height),
            after=distribution(np.r_[new_dist,new_reverse],height), source_boundary_groups=len(seam_groups),
            maximum_pad_skin_seam_gap=seam_gap, passes=bool(new_dist.max()<1e-6 and new_reverse.max()<1e-6 and seam_gap<1e-6))
        if folder is not None:
            output = Path(folder);output.mkdir(parents=True,exist_ok=True)
            if name in ('rest','standing','elbow-flex-60','arms-raised'):
                ids = np.unique(pad(rr).faces)
                for view in ('front-right','back-right'):
                    cam = camera(rr.vertices[ids],view,420)
                    cam.span *= 1.3  # Fixed reference framing margin; same for all panels.
                    tile = Image.new('RGB',(1260,470),(24,24,24));draw=ImageDraw.Draw(tile)
                    for i,(g,label) in enumerate(zip((rr,oo,nn),('Original HCTP surface / PSP rig','Accepted PSP / before','Protected pad / after'))):
                        render = raster(g,cam);rgb=render['rgb'];fids=render['face_ids'];valid=fids>=0
                        is_pad=np.zeros(fids.shape,dtype=bool)
                        is_pad[valid]=np.asarray(g.face_textures)[fids[valid]]==TEXTURE
                        gray=rgb[is_pad,0].astype(float)/220
                        rgb[is_pad]=np.clip(gray[:,None]*np.array([75,155,245]),0,255).astype('uint8')
                        tile.paste(Image.fromarray(rgb),(i*420,30));draw.text((i*420+8,8),label,fill='white')
                    draw.text((8,456),name+' / '+view+' | Same camera and pose; pad highlighted blue | CPU QA render',fill='white')
                    filename=name+'-'+view+'.png';tile.save(output/filename)
                    renders.append(dict(file=filename,pose=name,view=view,camera=cam.describe()))
    cranial = descendant_names(before,'kubi')
    columns = [i for i,n in enumerate(old.bone_names) if n in cranial]
    ids = np.flatnonzero(old.weights[:,columns].sum(1)>1e-7)
    lookup = {tuple(record):i for i,record in enumerate(new.vertex_records)}
    matches = np.array([lookup[tuple(old.vertex_records[i])] for i in ids])
    if not np.array_equal(old.vertices[ids],new.vertices[matches]) or not np.array_equal(old.weights[ids],new.weights[matches]):
        raise ValueError('Accepted facial/neck geometry or weights changed')
    face_probes = {}
    for name,probe in probes().items():
        a,_=skin(old,probe);b,_=skin(new,probe)
        delta=float(np.linalg.norm(a.vertices[ids]-b.vertices[matches],axis=1).max())
        face_probes[name]=dict(cranial_records=len(ids),maximum_delta_vs_accepted=delta,passes=delta==0)
    other_pose_checks = {}
    for name,controls in POSES.items():
        a,b=posed(old,controls),posed(new,controls)
        delta=float(np.linalg.norm(a.vertices[ids]-b.vertices[matches],axis=1).max())
        other_pose_checks[name]=dict(facial_neck_maximum_delta=delta,passes=delta==0)
    passed = all(m['passes'] for m in metrics.values()) and all(m['passes'] for m in face_probes.values()) and all(m['passes'] for m in other_pose_checks.values())
    return dict(status='pass' if passed else 'fail', pad_poses=metrics,
        eye_jaw_neck_probes=face_probes, full_suite_facial_identity=other_pose_checks,renders=renders,
        limitations=['Source-aligned pad is posed on the accepted PSP skeleton to isolate geometry/weights; original HCTP and PSP elbow bind pivots differ.',
                    'Controller probes are analytical stress tests, not captured SVR game animations.'],
        reference='Original aligned HCTP surface and source-supported mapped weights; no nonuniform scaling or vertex-index assumption')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-stage','baseline','candidate','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source=json.loads(a.source_stage.read_text())
    old=audit_yobj(next(r for s,r in sections(a.baseline.read_bytes()) if s['id']==2))
    new=audit_yobj(a.candidate.read_bytes())
    report=evaluate(source,old,new,a.output/'renders')
    write_json(a.output/'report.json',report)
    print(json.dumps(dict(status=report['status'],pad_poses=len(report['pad_poses']),eye_jaw_neck_probes=len(report['eye_jaw_neck_probes']),
        rest_before_p95=report['pad_poses']['rest']['before']['p95'],rest_after_p95=report['pad_poses']['rest']['after']['p95']),indent=2))


if __name__=='__main__':main()
