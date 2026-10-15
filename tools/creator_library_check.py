"""Reproduce prepared-library checks without modifying a source or baseline."""
import argparse
from collections import Counter
from pathlib import Path
import tempfile

from model_creator.core import PARTS, assemble, build, digest, dump, qa
from model_creator.library import Library, compatible, create_project


def check(output, *, resolution=128):
    output=Path(output)
    if output.exists():raise FileExistsError('Use a new validation directory')
    output.mkdir(parents=True);library=Library();sources=[library.source(i) for i in range(len(library.entries))]
    originals=[];pairs=[];trials=[];builds=[]
    for s in sources:
        raw,textures,r=assemble([s],dict.fromkeys(PARTS,0),library=True);q=qa(raw,r,library=True)
        originals.append(dict(label=s['label'],sha256=s['sha256'],bytes=len(s['data']),
            native_audit=True,analytical_poses=len(q['poses']),local_axis_poses=len(q['local_axis_poses']),descriptor_groups=s['model']['report']['descriptor_mesh_counts']))
    for i in range(len(sources)):
        for j in range(i+1,len(sources)):
            choices=dict(Head=1,Torso=0,Arms=0,Legs=0)
            try:review=compatible([sources[i],sources[j]],choices);reason=None
            except ValueError as exc:reason=str(exc)
            pairs.append(dict(a=sources[i]['label'],b=sources[j]['label'],body_bind_compatible=reason is None and not review.get('body_bind_differences'),branch_hierarchy_compatible=reason is None,reason=reason))
    base=next(s for s in sources if s['label']=='Batista')
    for s in sources:
        for part in PARTS:
            choices=dict.fromkeys(PARTS,0);choices[part]=1
            try:
                raw,textures,r=assemble([base,s],choices,library=True);q=qa(raw,r,library=True)
                row=dict(donor=s['label'],part=part,passed=True,native_audit=True,poses=len(q['poses']),
                    maximum_interior_pose_error=max((p['maximum_source_position_difference'] for p in r.get('interior_pose_comparison',{}).values()),default=0.),
                    maximum_local_axis_interior_pose_error=max((p['maximum_source_position_difference'] for p in r.get('local_axis_interior_pose_comparison',{}).values()),default=0.),shared_neck_fit=r.get('shared_neck_fit'),
                    unstitched_ambiguous_records=sum(x['unstitched_internal_records'] for x in r['seams']))
            except ValueError as exc:row=dict(donor=s['label'],part=part,passed=False,withheld_reason=str(exc))
            trials.append(row);print(row,flush=True)
    # Serialized PAC checks exercise every multi-descriptor head, extra weighted
    # controller example and a four-donor recipe. No arbitrary texture reduction.
    recipes=[]
    for label in ('Chris-Jericho','CM-Punk-Ring','Joey-Mercury-Ring','Yoshi-Tatsu','Zack-Ryder','Umaga (2)'):
        recipes.append(dict.fromkeys(PARTS,'Batista')|{'Head':label})
    recipes.extend([dict(Head='Sabu-Ring',Torso='Sabu-Ring',Arms='Booker-T',Legs='Sabu-Ring'),
        dict(Head='Yoshi-Tatsu',Torso='Batista',Arms='Chris-Benoit',Legs='Christian')])
    for number,recipe in enumerate(recipes):
        selected=[next(s for s in sources if s['label']==label) for label in sorted(set(recipe.values()))]
        choices={p:next(i for i,s in enumerate(selected) if s['label']==label) for p,label in recipe.items()}
        project=create_project(selected,choices,output/f'project-{number:02d}')
        try:
            r=build(project,choices,output/f'build-{number:02d}',resolution=resolution,library=True,allow_oversize=True)
            row=dict(recipe=recipe,passed=True,within_budget=r['within_budget'],budget_warning=r.get('budget_warning'),pac_bytes=r['pac_bytes'],pac_sha256=r['pac_sha256'],
                descriptor_groups=r['qa']['native_structural_audit']['descriptor_mesh_counts'],
                all_textures_original=r['textures_byte_exact'],original_interior_preserved=r.get('readback_attributes_and_topology',True),
                poses=len(r['qa']['poses']),unrelated_sections_identical=r.get('unrelated_stored_sections_identical',[]))
        except ValueError as exc:row=dict(recipe=recipe,passed=False,withheld_reason=str(exc))
        builds.append(row);print(row,flush=True)
    unchanged=all(digest(Path(s['path']).read_bytes())==s['sha256'] for s in sources)
    report=dict(schema='psp-model-creator.library-validation/1',originals_unchanged=unchanged,
        original_models=originals,body_bind_pairs=pairs,individual_part_trials=trials,serialized_builds=builds,
        summary=dict(originals=len(originals),body_bind_pairs=len(pairs),body_bind_pairs_compatible=sum(p['body_bind_compatible'] for p in pairs),
            individual_part_trials=len(trials),part_trials_passed=sum(t['passed'] for t in trials),
            serialized_builds=len(builds),builds_passed=sum(t['passed'] for t in builds),builds_within_budget=sum(t.get('within_budget',False) for t in builds)),
        runtime_status='Analytical/native checks only. PPSSPP validation of new mixed assemblies remains required.',
        coverage='All originals; all pair body binds; each donor part against Batista; eight actual PAC recipes. Not every four-way combination.')
    dump(output/'report.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    print(check(a.output)['summary'])
