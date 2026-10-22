import copy
import unittest
from tools.wwe13_uv_seams import seam_positions


class UVSeamTests(unittest.TestCase):
    def model(self, *, second_uv=(.5, .5), texture=0):
        def mesh(index, uv, tid):
            return dict(index=index, bone_palette=[0,1],
                        vertices=[dict(position=p, uv=t, weights=[index,1-index])
                                  for p,t in zip([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
                                                 [list(uv),[1.,0.],[0.,1.]])],
                        materials=[dict(texture_id=tid,triangles=[[0,1,2]])])
        return dict(meshes=[mesh(0,(0.,0.),0),mesh(1,second_uv,texture)])

    def test_uv_contact_is_locked_without_welding_or_editing_weights(self):
        model=self.model(); before=copy.deepcopy(model)
        self.assertEqual(seam_positions(model), {(0.,0.,0.)})
        self.assertEqual(model,before)

    def test_matching_corners_do_not_create_locks(self):
        self.assertEqual(seam_positions(self.model(second_uv=(0.,0.))), set())

    def test_distinct_material_binding_is_a_seam(self):
        self.assertEqual(len(seam_positions(self.model(second_uv=(0.,0.),texture=1))),3)

    def test_unreferenced_corner_does_not_create_a_lock(self):
        model=self.model(second_uv=(0.,0.))
        model['meshes'][0]['vertices'].append(dict(position=[0.,0.,0.],uv=[.8,.8],weights=[.2,.8]))
        self.assertEqual(seam_positions(model),set())

    def test_clothing_scope_does_not_add_hand_or_head_locks(self):
        for region in ('Hands','Head','Eyes','Mouth','Hair'):
            model=self.model()
            for mesh in model['meshes']:mesh['region']=region
            before=copy.deepcopy(model)
            self.assertEqual(seam_positions(model),{(0.,0.,0.)})
            self.assertEqual(seam_positions(model,regions=('Arms','Torso','Legs')),set())
            self.assertEqual(model,before)

    def test_clothing_regions_retain_existing_contacts_without_attribute_edits(self):
        for region in ('Arms','Torso','Legs'):
            model=self.model()
            for mesh in model['meshes']:mesh['region']=region
            before=copy.deepcopy(model)
            self.assertEqual(seam_positions(model,regions=('Arms','Torso','Legs')),{(0.,0.,0.)})
            self.assertEqual(model,before)

    def test_excluded_region_cannot_create_a_phantom_clothing_contact(self):
        model=self.model();model['meshes'][0]['region']='Arms';model['meshes'][1]['region']='Hands'
        self.assertEqual(seam_positions(model,regions=('Arms','Torso','Legs')),set())


if __name__=='__main__':unittest.main()
