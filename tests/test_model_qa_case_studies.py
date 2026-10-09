"""Known-defect regression from portable exported surfaces and unchanged PACs."""
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np
from PIL import Image

from model_qa.geometry import Geometry,geometry,read_model
from model_qa.metrics import detect,measure
from model_qa.regions import Region
from model_qa.render import Camera,raster


class CaseStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]
        cls.bundle=zipfile.ZipFile(cls.root/'downloads/HCTP-Model-QA-0.1-study.zip')
        cls.reports={name:cls.json(name+'/report.json') for name in ('lance-defect','lance-accepted','jericho')}

    @classmethod
    def tearDownClass(cls):cls.bundle.close()

    @classmethod
    def json(cls,path):return json.loads(cls.bundle.read(path))

    def mesh(self,case,kind,pose=None):
        with np.load(io.BytesIO(self.bundle.read(case+'/geometry/'+kind+'.npz'))) as z:
            vertices,faces,weights=z['vertices'],z['faces'],z['weights']
        rig='source' if kind=='reference' else 'candidate'
        model=self.json(case+'/geometry/'+rig+'-rig.json')
        g=Geometry(vertices,faces,weights,model['weight_bones'],['QA']*len(faces),[[0,i] for i in range(len(vertices))],model)
        if pose:
            g=copy.copy(g)
            with np.load(io.BytesIO(self.bundle.read(case+'/geometry/'+pose+'-'+('reference' if kind!='candidate' else 'candidate')+'.npz'))) as z:g.vertices=z['vertices']
        return g

    def rois(self,case,names):
        report=self.reports[case]
        return {name:Region(name,np.array(report['rest']['regions'][name]['roi']['lower']),np.array(report['rest']['regions'][name]['roi']['upper']),()) for name in names}

    def test_archive_crc_manifests_and_local_report_links(self):
        self.assertIsNone(self.bundle.testzip())
        manifests=['manifest.json']+[name+'/manifest.json' for name in self.reports]
        for path in manifests:
            prefix=path[:-len('manifest.json')]
            for relative,expected in self.json(path)['sha256'].items():
                self.assertEqual(hashlib.sha256(self.bundle.read(prefix+relative)).hexdigest(),expected)
        for case,r in self.reports.items():
            self.assertIn(case+'/report.html',self.bundle.namelist())
            self.assertEqual({g['view'] for g in r['gallery'] if g['region']=='whole'}, {'front','back','left','right','front-left','front-right','back-left','back-right'})
            for entry in r['gallery']:self.assertIn(case+'/'+entry['file'],self.bundle.namelist())

    def test_lance_rear_defect_recomputed_and_not_hidden_by_silhouette(self):
        for case in ('lance-defect','lance-accepted'):
            r=self.reports[case];source=self.mesh(case,'reference');candidate=self.mesh(case,'candidate')
            measured,_=measure(source,candidate,self.rois(case,['buttocks','pelvis']),r['reference_height'],count=24000)
            for region in ('buttocks','pelvis'):
                self.assertAlmostEqual(measured['regions'][region]['distance']['p95_height'],r['rest']['regions'][region]['distance']['p95_height'],places=12)
                self.assertTrue(any(f['region']==region and f['pose']=='rest' for f in detect(measured,r['thresholds'])))
            self.assertGreater(r['rest']['regions']['buttocks']['views']['back']['inward_depth_p95_height'],.03)
            first=[x for x in r['defect_first_appearance'] if x['region']=='buttocks' and x['pose']=='rest']
            self.assertEqual(first[0]['first_flagged_supplied_stage'],'regional-reduction')
            self.assertLess(r['stage_trace'][0]['rest']['regions']['buttocks']['distance']['p95_height'],1e-12)
        self.assertGreater(self.reports['lance-accepted']['rest']['regions']['buttocks']['views']['back']['silhouette_iou'],.995)
        self.assertLess(self.reports['lance-accepted']['rest']['regions']['buttocks']['distance']['p95_height'],self.reports['lance-defect']['rest']['regions']['buttocks']['distance']['p95_height'])

    def test_jericho_static_jaw_passes_but_pose_defect_precedes_reduction(self):
        case='jericho';r=self.reports[case];rois=self.rois(case,['jaw','chin'])
        reference,candidate=self.mesh(case,'reference'),self.mesh(case,'candidate')
        rest,_=measure(reference,candidate,rois,r['reference_height'],count=24000)
        self.assertEqual(detect(rest,r['thresholds']),[])
        for pose in ('neck-turn','jaw-18'):
            result,_=measure(self.mesh(case,'reference',pose),self.mesh(case,'candidate',pose),rois,r['reference_height'],reference,candidate,count=24000)
            self.assertAlmostEqual(result['regions']['jaw']['distance']['p95_height'],r['poses'][pose]['regions']['jaw']['distance']['p95_height'],places=12)
            self.assertTrue(any(f['region']=='jaw' and f['kind']=='pose-dependent-deformation' for f in detect(result,r['thresholds'],pose,rest)))
            first=[x for x in r['defect_first_appearance'] if x['region']=='jaw' and x['pose']==pose]
            self.assertEqual(first[0]['first_flagged_supplied_stage'],'hybrid-weight-transfer')
        self.assertLess(r['stage_trace'][0]['rest']['regions']['jaw']['distance']['p95_height'],1e-7)
        source_mass=r['influence_diagnostics']['source']['jaw']['mean_influence_mass']
        candidate_mass=r['influence_diagnostics']['candidate']['jaw']['mean_influence_mass']
        self.assertLess(source_mass['body']+source_mass['neck'],.03)
        self.assertGreater(candidate_mass['body']+candidate_mass['neck'],.15)

    def test_pac_identity_native_validity_and_exported_geometry(self):
        for case,r in self.reports.items():
            pac=self.root/'downloads'/Path(r['inputs']['candidate']).name
            self.assertEqual(hashlib.sha256(pac.read_bytes()).hexdigest(),r['preserved_previous_candidate_sha256'])
            self.assertTrue(r['inputs_unchanged']);self.assertFalse(r['automatic_correction_enabled'])
            self.assertFalse(r['can_replace_best_model']);self.assertEqual(r['corrections_attempted'],[])
            self.assertLessEqual(pac.stat().st_size,148000)
            self.assertTrue(r['format']['native_psp_audit_passed'])
            actual=geometry(read_model(pac));exported=self.mesh(case,'candidate')
            np.testing.assert_array_equal(actual.vertices,exported.vertices)
            np.testing.assert_array_equal(actual.faces,exported.faces)
            np.testing.assert_array_equal(actual.weights,exported.weights)
            self.assertFalse(r['alignment']['nonuniform_scaling'])

    def test_comparison_images_render_the_exact_exported_candidate(self):
        for case,pose,region,view in [('lance-accepted','rest','buttocks','back-right'),('jericho','jaw-18','jaw','left')]:
            r=self.reports[case]
            entry=next(x for x in r['gallery'] if (x['pose'],x['region'],x['view'])==(pose,region,view))
            g=self.mesh(case,'candidate',None if pose=='rest' else pose)
            c=entry['camera']
            cam=Camera(c['name'],*[np.array(c[k]) for k in ('center','right','up','direction')],c['span'],c['resolution'])
            rendered=raster(g,cam)['rgb']
            path=case+'/'+entry['file'][:-4]+'-candidate.png'
            saved=np.array(Image.open(io.BytesIO(self.bundle.read(path))).convert('RGB'))
            np.testing.assert_array_equal(rendered,saved)

    def test_calibration_holds_out_known_defects(self):
        profile=self.json('tolerances.json')
        lance=next(c for c in profile['calibration_cases'] if 'Lance' in c['label'])
        jericho=next(c for c in profile['calibration_cases'] if 'Jericho' in c['label'])
        self.assertNotIn('buttocks',lance['trusted_regions']);self.assertNotIn('pelvis',lance['trusted_regions'])
        self.assertNotIn('jaw',jericho['trusted_regions'])
        self.assertEqual(profile['animation_extra_p95_height'],.002)
        self.assertIn('provisional',profile['animation_calibration'])


if __name__=='__main__':unittest.main()
