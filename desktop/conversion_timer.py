"""Monotonic conversion clock and locally learned, explicitly approximate ETA.

Progress percentages describe pipeline stages, not equal amounts of time. A
completed run records its stage timing curve; future runs of the same platform,
texture mode and geometry/role settings use the median of recent curves. New
profiles use a provisional progress-rate estimate after initial startup.
"""
import bisect
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import time


def duration(seconds):
    seconds=max(0,int(math.ceil(seconds)))
    h,remainder=divmod(seconds,3600);m,s=divmod(remainder,60)
    return f'{h}:{m:02d}:{s:02d}'if h else f'{m:02d}:{s:02d}'


def profile(options):
    return '|'.join(str(options.get(k,default))for k,default in
                    [('source_format','hctp'),('texture_mode','Default'),('costume_role','ring'),('wii_geometry','Standard'),('downgrade_steps',0)])


def valid_trace(value):
    try:
        total=value['total_seconds'];points=value['points']
        if isinstance(total,bool)or not isinstance(total,(int,float))or not math.isfinite(total)or not 0<total<=86400:return False
        if not isinstance(points,list)or not 2<=len(points)<=102:return False
        previous=(-1.,-1.)
        for p,t in points:
            if not all(isinstance(v,(int,float))and not isinstance(v,bool)and math.isfinite(v)for v in (p,t)):return False
            if not previous[0]<p<=100 or not previous[1]<=t<=total:return False
            previous=p,t
        return points[0]==[0,0]and points[-1]==[100,total]
    except (KeyError,TypeError,ValueError):return False


def read_history(path):
    try:
        path=Path(path)
        if path.stat().st_size>2*1024*1024:return {}
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema')!='conversion-timings/1':return {}
        return {k:[r for r in rows[-12:]if valid_trace(r)]for k,rows in value['profiles'].items()
                if isinstance(k,str)and len(k)<=256 and isinstance(rows,list)}
    except (OSError,ValueError,TypeError,AttributeError,KeyError):return {}


def save_trace(path,key,trace):
    if not valid_trace(trace):return False
    path=Path(path);history=read_history(path);rows=history.pop(key,[])
    history[key]=(rows+[trace])[-12:]
    history=dict(list(history.items())[-64:])
    fd,name=tempfile.mkstemp(prefix='timings-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8')as stream:
            json.dump(dict(schema='conversion-timings/1',profiles=history),stream,allow_nan=False)
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)
    return True


def expected_elapsed(trace,percent):
    points=trace['points'];ps=[r[0]for r in points]
    i=bisect.bisect_left(ps,percent)
    if i==0:return 0.
    if i>=len(points):return float(trace['total_seconds'])
    a,t=points[i-1];b,u=points[i]
    return t+(u-t)*(percent-a)/(b-a)


class ConversionTimer:
    def __init__(self,history=(),*,clock=time.monotonic):
        self.clock=clock;self.history=[r for r in history if valid_trace(r)]
        self.started=None;self.stopped=None;self.status='idle';self.percent=0.
        self.points=[[0,0]];self.deadline=None;self.cancelling=False

    def start(self):
        self.started=self.clock();self.stopped=None;self.status='running';self.percent=0.
        self.points=[[0,0]];self.cancelling=False
        self.deadline=self.started+statistics.median(r['total_seconds']for r in self.history)if self.history else None

    @property
    def elapsed(self):
        if self.started is None:return 0.
        return max(0.,(self.stopped if self.stopped is not None else self.clock())-self.started)

    def observe(self,percent,elapsed_seconds=None):
        if self.status!='running' or self.cancelling:return
        if isinstance(percent,bool)or not isinstance(percent,(int,float))or not math.isfinite(percent):return
        if not self.percent<percent<=100:return
        current=self.elapsed
        t=elapsed_seconds if isinstance(elapsed_seconds,(float,int))and not isinstance(elapsed_seconds,bool)and math.isfinite(elapsed_seconds)else current
        # Workers may start later than the GUI. Bad/out-of-order timestamps are
        # ignored, rather than allowing negative time or clock jumps into ETA.
        if not self.points[-1][1]<=t<=current+2:t=current
        t=max(self.points[-1][1],min(current,float(t)))
        self.percent=float(percent);self.points.append([self.percent,t])
        if percent>=100:self.deadline=None;return
        predictions=[]
        for trace in self.history:
            expected=expected_elapsed(trace,percent)
            scale=max(.5,min(3.,t/expected))if expected>3 and t>3 else 1.
            predictions.append(t+max(1.,(trace['total_seconds']-expected)*scale))
        if predictions:self.deadline=self.started+statistics.median(predictions)
        elif t>=3 and percent>=5:self.deadline=self.started+max(t+1,t*100/percent)

    def cancel(self):
        if self.status=='running':self.cancelling=True;self.deadline=None

    def finish(self,status):
        if self.status!='running':return None
        if status not in ('completed','cancelled','failed'):raise ValueError('Invalid timer completion status.')
        self.stopped=self.clock();self.status=status;self.deadline=None
        if status!='completed' or self.elapsed<=0:return None
        points=[p for p in self.points if p[0]<100]+[[100,self.elapsed]]
        trace=dict(total_seconds=self.elapsed,points=points)
        return trace if valid_trace(trace)else None

    def text(self):
        if self.status=='idle':return 'Elapsed: -- | Estimated remaining: --'
        elapsed=duration(self.elapsed)
        if self.status!='running':return self.status.capitalize()+' in '+elapsed
        if self.cancelling:return 'Elapsed: '+elapsed+' | Cancelling...'
        if self.percent>=100:return 'Elapsed: '+elapsed+' | Finishing...'
        # A first run can sit inside its first long stage before another event.
        # Start one provisional countdown once enough startup time has elapsed;
        # do not keep moving the deadline forward on every UI tick.
        if self.deadline is None and self.percent>=5 and self.elapsed>=3 and not self.history:
            self.deadline=self.started+max(self.elapsed+1,self.elapsed*100/self.percent)
        if self.deadline is None:return 'Elapsed: '+elapsed+' | Estimated remaining: calculating...'
        remaining=self.deadline-self.clock()
        if remaining<=0:return 'Elapsed: '+elapsed+' | Estimated remaining: updating (stage taking longer)'
        return 'Elapsed: '+elapsed+' | Estimated remaining: ~'+duration(remaining)
