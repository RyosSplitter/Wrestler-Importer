"""Package existing read-only QA reports; no conversion or correction is performed."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(reports, output, archive, profile, calibration):
    reports,output,archive,profile=map(Path,(reports,output,archive,profile))
    if output.exists() or archive.exists():
        raise FileExistsError('Refusing to overwrite a previous study or archive')
    names=('lance-defect','lance-accepted','jericho')
    data={name:json.loads((reports/name/'report.json').read_text()) for name in names}
    for name,report in data.items():
        if not report['inputs_unchanged'] or report['corrections_attempted'] or report['can_replace_best_model']:
            raise ValueError('Study requires an immutable comparison-only report: '+name)
        manifest=json.loads((reports/name/'manifest.json').read_text())
        for relative,expected in manifest['sha256'].items():
            if digest(reports/name/relative)!=expected:raise ValueError('Report input mismatch: '+relative)
    output.mkdir(parents=True)
    for name in names:shutil.copytree(reports/name,output/name)
    shutil.copy2(profile,output/'tolerances.json')
    (output/'calibration').mkdir()
    for path in calibration:
        path=Path(path)
        shutil.copy2(path,output/'calibration'/(path.parent.name+'-'+path.name))
    summary={'mode':'comparison-only; no PAC correction','cases':{}}
    for name,r in data.items():
        summary['cases'][name]=dict(source=r['inputs']['source'],candidate=r['inputs']['candidate'],
            candidate_sha256=r['preserved_previous_candidate_sha256'],format=r['format'],alignment=r['alignment'],
            buttocks_rest=r['rest']['regions']['buttocks']['distance'],jaw_rest=r['rest']['regions']['jaw']['distance'],
            jaw_18=r['poses']['jaw-18']['regions']['jaw']['distance'],neck_turn_jaw=r['poses']['neck-turn']['regions']['jaw']['distance'],
            flags=r['flags'],first_appearance=r['defect_first_appearance'],influence_diagnostics=r['influence_diagnostics'])
    dump=lambda path,value:Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    dump(output/'summary.json',summary)
    e=html.escape
    images=[('Lance: earlier known concavity','lance-defect/renders/rest-buttocks-back-right.png'),
            ('Lance: accepted version still has a posterior deficit','lance-accepted/renders/rest-buttocks-back-right.png'),
            ('Jericho: static jaw control','jericho/renders/rest-jaw-left.png'),
            ('Jericho: jaw opening on identical PSP rigs','jericho/renders/jaw-18-jaw-left.png'),
            ('Jericho: neck-turn jaw deviation','jericho/renders/neck-turn-jaw-right.png')]
    rows=[]
    for name,r in data.items():
        rows.append('<tr><td><a href="'+name+'/report.html">'+name+'</a></td>'
            '<td>%.4f%%</td><td>%.4f%%</td><td>%.4f%%</td><td>%.4f%%</td><td>%d bytes</td></tr>'%(
                100*r['rest']['regions']['buttocks']['distance']['p95_height'],
                100*r['rest']['regions']['jaw']['distance']['p95_height'],
                100*r['poses']['jaw-18']['regions']['jaw']['distance']['p95_height'],
                100*r['poses']['neck-turn']['regions']['jaw']['distance']['p95_height'],r['format']['pac_bytes']))
    text='''<!doctype html><html><head><meta charset="utf-8"><title>HCTP model QA study</title>
<style>body{font:16px system-ui;background:#202329;color:#ddd;max-width:1300px;margin:30px auto;padding:18px}a{color:#8ecaff}table{border-collapse:collapse}td,th{padding:12px;border:1px solid #555}img{width:100%}figure{margin:32px 0}.notice{padding:18px;background:#333b48}</style></head><body>
<h1>HCTP model quality review</h1><p class="notice">Read-only geometric comparisons. No PAC changed, and no automated correction was attempted. CPU clay renders show shape; they are not textured Noesis screenshots or PPSSPP footage.</p>
<p>Open a case report for interactive image wipes, regional metrics, heatmaps, native-format checks and stage traces. Percentages below are p95 bidirectional surface distance divided by original reference height.</p>
<table><tr><th>Case/report</th><th>Rear rest</th><th>Jaw rest</th><th>Jaw opening 18°</th><th>Neck turn, jaw region</th><th>Unchanged PAC size</th></tr>'''+''.join(rows)+'''</table>
<p><b>Lance:</b> rear surface error first appears in the supplied regional-reduction stage and grows in the earlier rear-waist edit. The accepted later version improves the measured error but still needs posterior review. Earlier documentation reversed front/back material labels; it restored front surfaces rather than the actual rear.</p>
<p><b>Jericho:</b> no static jaw flag. Jaw/neck pose error is already measurable in the supplied hybrid-weight-transfer stage, before reduction. Original-weight and final-weight meshes use identical PSP bones, isolating transferred weights from rig-pivot differences. Original-HCTP-rig controls are in the full JSON report.</p>
<p>Thresholds are provisional, calibrated only on selected accepted static regions. Lance's rear and Jericho's animated jaw are held out. Synthetic poses cannot establish game animation correctness or crash safety. Open patches support projected depth proxies, not closed volume claims.</p>
<p><a href="summary.json">Study summary JSON</a> · <a href="tolerances.json">Provisional tolerances</a> · <a href="manifest.json">Study SHA-256 manifest</a></p>'''
    for label,path in images:text+='<figure><figcaption>'+e(label)+'</figcaption><a href="'+e(path)+'"><img src="'+e(path)+'"></a></figure>'
    (output/'index.html').write_text(text+'</body></html>',encoding='utf-8')
    (output/'README.txt').write_text('Open index.html after extracting this entire archive.\nNo PAC files or corrections are included.\nGeometry OBJ/NPZ exports are QA-only, with canonical X=left, Y=up, Z=front.\nReports and comparison image pairs use identical cameras and lighting.\nCandidates remain available in the existing repository downloads; hashes are recorded.\nSee docs/model-qa.md in the repository for CLI usage and limitations.\n',encoding='utf-8')
    dump(output/'manifest.json',{'sha256':{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(output)))
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise RuntimeError('Archive CRC check failed')
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,sha256=digest(archive))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports',required=True);p.add_argument('--output',required=True)
    p.add_argument('--archive',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--calibration',action='append',default=[])
    a=p.parse_args();build(a.reports,a.output,a.archive,a.profile,a.calibration)
