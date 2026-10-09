"""python -m model_qa compare --source HCTP.pac --converted PSP.pac --output NEW"""
import argparse
import json
from pathlib import Path
from .metrics import calibrate
from .pipeline import dump,run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('compare');p.add_argument('--source',required=True,type=Path);p.add_argument('--converted',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--profile',type=Path);p.add_argument('--stage',action='append',default=[],metavar='LABEL=TARGET_SPACE_FILE')
    p.add_argument('--samples',type=int,default=16000);p.add_argument('--resolution',type=int,default=320)
    p.add_argument('--no-animation',action='store_true');p.add_argument('--no-renders',action='store_true');p.add_argument('--fail-on-review',action='store_true')
    p.add_argument('--save-depth',action='store_true',help='Also save float32 per-view depth arrays; larger reports')
    p=sub.add_parser('calibrate');p.add_argument('--controls',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.command=='calibrate':
        if args.output.exists():raise FileExistsError('Will not overwrite a calibration profile')
        manifest=json.loads(args.controls.read_text());controls=[]
        for case in manifest['controls']:
            path=args.controls.parent/case['report'];controls.append((case['label'],json.loads(path.read_text()),case['trusted_regions']))
        args.output.parent.mkdir(parents=True,exist_ok=True);dump(args.output,calibrate(controls));return 0
    stages=[]
    for raw in args.stage:
        label,sep,path=raw.partition('=')
        if not sep or not label or not path:raise ValueError('Stage must be LABEL=PATH in target model space')
        stages.append(dict(label=label,path=path,space='target'))
    profile=json.loads(args.profile.read_text()) if args.profile else None
    r=run(args.source,args.converted,args.output,profile=profile,stages=stages,samples=args.samples,resolution=args.resolution,
          animations=not args.no_animation,renders=not args.no_renders,save_depth=args.save_depth,progress=lambda s:print(s,flush=True))
    print(json.dumps(dict(output=str(args.output),review_flags=len(r['unresolved_review']),inputs_unchanged=r['inputs_unchanged'],corrections_attempted=[])))
    return 2 if args.fail_on_review and r['unresolved_review'] else 0


if __name__=='__main__':raise SystemExit(main())
