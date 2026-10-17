"""Asset-free regressions for the JBI finger-role failure; no game data."""
import copy
import unittest

import numpy as np

from tools.jbi_rig import (_segment_query, digit_review, finger_chains,
    refine_arms_chain_control as refine_arms, refine_arms as refine_bind_arms,
    rebind_arm_reference)
from tools.sym_rig import arrays
from tools.weight_trial_review import deform


def fixture(segments):
    bones=[dict(index=0,name='root',parent=-1,local_position=[0.,0.,0.],rotation=[0.,0.,0.])]
    vertices=[]
    for side,sign in [('l',1),('r',-1)]:
        parent=0
        for stem,distance in [('sakotsu',0.),('ninoude',1.),('ninoude_x',.25),('kote',.25),('kote_x',.25)]:
            i=len(bones);bones.append(dict(index=i,name=side+'_'+stem,parent=parent,
                local_position=[sign*distance,0.,0.],rotation=[0.,0.,0.]));parent=i
        hand=len(bones)
        bones.append(dict(index=hand,name=side+'_te',parent=parent,
            local_position=[sign*.25,0.,0.],rotation=[0.,0.,0.]))
        for digit in range(5):
            parent=hand
            suffixes=[1,0] if segments==2 else [0,1,2]
            for step,suffix in enumerate(suffixes):
                index=len(bones)
                bones.append(dict(index=index,name=f'{side}_yubi{digit}{suffix}',parent=parent,
                    local_position=[sign*.4,0.,digit*.2 if step==0 else 0.],rotation=[0.,0.,0.]))
                parent=index
                vertices.append(dict(position=[sign*(2.6+step*.4),.1,digit*.2],
                    normal=[0.,1.,0.],uv=[digit*.1,step*.1],color=[255]*4,
                    source_vertex_index=len(vertices),influence=index))
    vertices.append(dict(position=[0.,1.,0.],normal=[0.,1.,0.],uv=[0.,0.],color=[255]*4,
                         source_vertex_index=len(vertices),influence=0))
    for v in vertices:
        w=np.zeros(len(bones));w[v.pop('influence')]=1.;v['weights']=w.tolist()
    return dict(bones=bones,bone_count=len(bones),textures=['synthetic'],texture_count=1,
        meshes=[dict(index=0,bone_palette=list(range(len(bones))),vertices=vertices,
                     materials=[dict(texture_id=0,triangles=[[0,1,2]],strips=[])])])


def panel_donor(target):
    """Independent flat digit surfaces with known per-segment bone support."""
    target=copy.deepcopy(target);vertices=[];tris=[]
    for side,sign in [('l',1),('r',-1)]:
        chains=finger_chains(target,side)
        for digit in range(5):
            start=len(vertices)
            for level in range(4):
                for y in [-.15,.15]:
                    w=np.zeros(target['bone_count']);w[chains[digit][min(level,2)]]=1
                    vertices.append(dict(position=[sign*(2.4+level*.4),y,digit*.2],
                        normal=[0.,0.,1.],uv=[level/4,.5],color=[255]*4,weights=w.tolist()))
            for level in range(3):
                a=start+level*2;tris += [[a,a+1,a+2],[a+1,a+3,a+2]]
    target['meshes'][0]['vertices']=vertices
    target['meshes'][0]['materials'][0]['triangles']=tris
    return target


def trials():
    source=fixture(2);target=fixture(3);baseline=copy.deepcopy(source)
    baseline['bones']=copy.deepcopy(target['bones']);baseline['bone_count']=target['bone_count']
    baseline['meshes'][0]['bone_palette']=list(range(target['bone_count']))
    tb={b['name']:b['index'] for b in target['bones']}
    for v,sv in zip(baseline['meshes'][0]['vertices'],source['meshes'][0]['vertices']):
        source_index=int(np.argmax(sv['weights']));name=source['bones'][source_index]['name']
        wrong='l_yubi10' if name.startswith('l_yubi0') else 'r_yubi10' if name.startswith('r_yubi0') else (
            name[:-1]+'0' if '_yubi' in name else name)
        w=np.zeros(target['bone_count']);w[tb[wrong]]=1.;v['weights']=w.tolist()
    return source,target,baseline


IDENTITY=dict(scale=1.,rotation=np.eye(3).tolist(),translation=[0.,0.,0.])


class JbiRigTests(unittest.TestCase):
    def test_chain_order_uses_hierarchy_instead_of_numeric_suffix(self):
        source=fixture(2);target=fixture(3)
        self.assertEqual([source['bones'][i]['name'] for i in finger_chains(source,'l')[1]],['l_yubi11','l_yubi10'])
        self.assertEqual([target['bones'][i]['name'] for i in finger_chains(target,'l')[1]],['l_yubi10','l_yubi11','l_yubi12'])

    def test_foreign_digit_negative_control_is_detected_and_removed(self):
        s,t,b=trials();before=copy.deepcopy(b);original=copy.deepcopy(s)
        result,report=refine_arms(s,t,b,IDENTITY)
        self.assertGreater(sum(r['wrong_digit_records'] for r in report['digit_review_before']),0)
        self.assertEqual(sum(r['wrong_digit_records'] for r in report['digit_review_after']),0)
        self.assertEqual(s,original);self.assertEqual(b,before)
        self.assertTrue(report['positions_exact']);self.assertTrue(report['unaffected_weights_exact'])
        np.testing.assert_array_equal(arrays(b)[0],arrays(result)[0])
        self.assertEqual(result['meshes'][0]['materials'],b['meshes'][0]['materials'])
        for x,y in zip(b['meshes'][0]['vertices'],result['meshes'][0]['vertices']):
            for key in ('normal','uv','color'):self.assertEqual(x[key],y[key])

    def test_independent_index_flex_does_not_move_thumb(self):
        s,t,b=trials();n,report=refine_arms(s,t,b,IDENTITY)
        p,old=arrays(b);_,new=arrays(n);_,sw=arrays(s)
        thumb=sw[:,finger_chains(s,'l')[0]].sum(1)>0
        index=sw[:,finger_chains(s,'l')[1]].sum(1)>0
        pose={'l_yubi10':('z',40)}
        bad=deform(b,p,old,pose);fixed=deform(n,p,new,pose)
        self.assertGreater(np.linalg.norm((bad-p)[thumb]),.1)
        np.testing.assert_allclose(fixed[thumb],p[thumb],atol=1e-12)
        self.assertGreater(np.linalg.norm((fixed-p)[index]),.1)

    def test_second_source_segment_maps_middle_not_same_suffix(self):
        s,t,b=trials();n,report=refine_arms(s,t,b,IDENTITY)
        mapping={r['source']:r['target'] for r in report['finger_mapping']}
        self.assertEqual(mapping['l_yubi10'],'l_yubi11')
        self.assertEqual(mapping['l_yubi11'],'l_yubi10')
        self.assertEqual(mapping['r_yubi00'],'r_yubi01')
        _,w=arrays(n)
        tips=[b['index'] for b in t['bones'] if '_yubi' in b['name'] and b['name'].endswith('2')]
        np.testing.assert_array_equal(w[:,tips],0.)
        np.testing.assert_allclose(w.sum(1),1.,atol=1e-12)

    def test_unhandled_and_ambiguous_chains_fail_closed(self):
        s,t,b=trials();t['bones'][finger_chains(t,'l')[0][1]]['parent']=0
        with self.assertRaisesRegex(ValueError,'Disconnected'):refine_arms(s,t,b,IDENTITY)
        s,t,b=trials();source_finger=finger_chains(s,'l')[0][0]
        s['meshes'][0]['vertices'][0]['weights'][source_finger]=.5
        helper=len(s['bones']);s['bones'].append(dict(index=helper,name='unknown_control',parent=0,
            local_position=[0.,0.,0.],rotation=[0.,0.,0.]));s['bone_count']+=1
        s['meshes'][0]['bone_palette'].append(helper)
        for i,v in enumerate(s['meshes'][0]['vertices']):v['weights'].append(.5 if i==0 else 0.)
        with self.assertRaisesRegex(ValueError,'unhandled source'):refine_arms(s,t,b,IDENTITY)

    def test_segment_warp_only_maps_donor_queries_without_input_mutation(self):
        points=np.array([[1.,.5,0.],[2.,0.,0.]])
        original=points.copy()
        q=_segment_query(points,np.array([0.,0.,0.]),np.array([2.,0.,0.]),
            np.array([3.,2.,0.]),np.array([3.,6.,0.]))
        np.testing.assert_allclose(q,[[2.,4.,0.],[3.,6.,0.]],atol=1e-12)
        np.testing.assert_array_equal(points,original)
        with self.assertRaisesRegex(ValueError,'Degenerate'):
            _segment_query(points,np.zeros(3),np.zeros(3),np.zeros(3),np.ones(3))

    def test_refinement_is_deterministic(self):
        s,t,b=trials();a,ra=refine_arms(s,t,b,IDENTITY);c,rc=refine_arms(s,t,b,IDENTITY)
        self.assertEqual(a,c);self.assertEqual(ra,rc)

    def test_bind_conversion_and_constrained_sampling_keep_digit_identity(self):
        s,t,b=trials();t=panel_donor(t)
        n,report=refine_bind_arms(s,t,b,IDENTITY)
        self.assertEqual(sum(r['wrong_digit_records'] for r in report['digit_review_after']),0)
        self.assertEqual(report['bind_reference_conversion']['maximum_rest_seam_gap'],0.)
        self.assertTrue(report['bind_reference_conversion']['unaffected_positions_exact'])
        self.assertFalse(report['positions_exact'])
        self.assertEqual(n['meshes'][0]['materials'],b['meshes'][0]['materials'])
        for a,c in zip(n['meshes'][0]['vertices'],b['meshes'][0]['vertices']):
            self.assertEqual(a['uv'],c['uv']);self.assertEqual(a['color'],c['color'])
        p,w=arrays(n);_,sw=arrays(s);thumb=sw[:,finger_chains(s,'l')[0]].sum(1)>0
        index=sw[:,finger_chains(s,'l')[1]].sum(1)>0
        moved=deform(n,p,w,{'l_yubi10':('z',35)})
        np.testing.assert_allclose(moved[thumb],p[thumb],atol=1e-12)
        self.assertGreater(np.linalg.norm((moved-p)[index]),.01)
        np.testing.assert_allclose(w.sum(1),1.,atol=1e-12)

    def test_bind_offsets_are_measured_in_matched_bone_frames(self):
        s,t,b=trials();original=copy.deepcopy(b)
        n,report=rebind_arm_reference(s,t,b,IDENTITY)
        # Synthetic thumb source proximal joint is x=2.4; PSP middle joint
        # is x=2.8. The original +0.2 local vertex offset must survive.
        self.assertAlmostEqual(n['meshes'][0]['vertices'][0]['position'][0],3.,places=6)
        self.assertEqual(b,original)
        for a,c in zip(n['meshes'][0]['vertices'],b['meshes'][0]['vertices']):
            self.assertEqual(a['weights'],c['weights'])

    def test_bind_cracks_are_rejected_without_averaging_source_records(self):
        s,t,b=trials()
        # Coincident geometry with distinct source thumb/index records is
        # intentional here. Incompatible proposed rest positions must fail.
        s['meshes'][0]['vertices'][2]['position']=s['meshes'][0]['vertices'][0]['position'].copy()
        b['meshes'][0]['vertices'][2]['position']=b['meshes'][0]['vertices'][0]['position'].copy()
        old=copy.deepcopy(b)
        with self.assertRaisesRegex(ValueError,'coincident source seam'):
            rebind_arm_reference(s,t,b,IDENTITY)
        self.assertEqual(b,old)


if __name__=='__main__':unittest.main()
