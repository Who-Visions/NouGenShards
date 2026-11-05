"""UDCT deterministic semantic character performance engine. Python 3.11+, stdlib only."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
import math, hashlib, json

TAU=2*math.pi

def clamp(x, lo=0.0, hi=1.0): return max(lo,min(hi,x))
def smooth(x):
    x=clamp(x); return x*x*(3-2*x)
def mix(a,b,w): return a+(b-a)*clamp(w)
def pulse(t, center, width): return math.exp(-0.5*((t-center)/max(width,1e-5))**2)
def stable_unit(seed, label, index):
    b=f'{seed}:{label}:{index}'.encode()
    return int.from_bytes(hashlib.blake2b(b,digest_size=8).digest(),'big')/2**64

def periodic_blink(t, seed, rate=0.22):
    # Randomized but deterministic intervals, independent of evaluation order.
    slot=int(math.floor(t/max(1/rate,0.1)))
    result=0.0
    for i in (slot-1,slot,slot+1):
        c=(i+0.15+0.7*stable_unit(seed,'blink',i))/rate
        w=0.055+0.035*stable_unit(seed,'blink-width',i)
        result=max(result,pulse(t,c,w))
    return clamp(result)

@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    kind: str
    value: float=1.0
    label: str=''
    def weight(self,t):
        if not self.start<=t<=self.end:return 0.0
        attack=min(0.12,max(0.01,(self.end-self.start)*0.2))
        release=attack
        return self.value*smooth((t-self.start)/attack)*smooth((self.end-t)/release)

@dataclass(frozen=True)
class Phoneme:
    start: float
    end: float
    symbol: str

@dataclass(frozen=True)
class Identity:
    name: str='NOU'
    seed: int=42017
    blink_rate: float=0.23
    breath_rate: float=0.21
    expressivity: float=0.65
    gesture_scale: float=0.55
    hair_sway: float=0.2

@dataclass(frozen=True)
class Performance:
    duration: float
    identity: Identity=field(default_factory=Identity)
    cues: tuple[Cue,...]=()
    phonemes: tuple[Phoneme,...]=()
    speech_energy: tuple[tuple[float,float],...]=()

@dataclass(frozen=True)
class Context:
    performance: Performance
    t: float
    def cue(self,kind):
        return clamp(sum(c.weight(self.t) for c in self.performance.cues if c.kind==kind))
    def energy(self):
        pts=self.performance.speech_energy
        if not pts:return 0.0
        if self.t<=pts[0][0]:return pts[0][1]
        for a,b in zip(pts,pts[1:]):
            if a[0]<=self.t<=b[0]:return mix(a[1],b[1],(self.t-a[0])/max(b[0]-a[0],1e-6))
        return pts[-1][1]
    def phoneme(self):
        for p in self.performance.phonemes:
            if p.start<=self.t<p.end:return p.symbol.upper()
        return 'REST'

class Module(Protocol):
    name: str
    def evaluate(self,c:Context)->dict[str,float]:...

class Eyes:
    name='eyes'
    def evaluate(self,c):
        i=c.performance.identity
        blink=periodic_blink(c.t,i.seed,i.blink_rate)
        attention=c.cue('attention'); glance=c.cue('glance_left')-c.cue('glance_right')
        return {'eye.blink.L':blink,'eye.blink.R':blink,
                'eye.gaze_x':clamp(glance,-1,1),
                'eye.gaze_y':clamp(c.cue('look_up')-c.cue('look_down'),-1,1),
                'eye.widen':clamp(0.15*attention+0.25*c.cue('surprise'))}
class Brows:
    name='brows'
    def evaluate(self,c):
        lift=clamp(0.45*c.cue('surprise')+0.2*c.cue('emphasis'))
        furrow=clamp(0.6*c.cue('concern')+0.2*c.cue('focus'))
        return {'brow.raise.L':lift,'brow.raise.R':lift*0.94,'brow.furrow':furrow}
class Cheeks:
    name='cheeks'
    def evaluate(self,c):
        smile=c.cue('smile')
        return {'cheek.raise.L':clamp(smile*.7),'cheek.raise.R':clamp(smile*.68),'cheek.puff':clamp(c.cue('puff'))}
VISEMES={
    'REST':(0,0,0,0),'AA':(.85,.15,0,0),'AH':(.7,.1,0,0),
    'EH':(.55,.15,0,0),'IH':(.3,.35,0,0),'IY':(.25,.65,0,0),
    'OW':(.55,0,.85,0),'UW':(.25,0,.95,0),'M':(0,0,0,1),
    'B':(0,0,0,1),'P':(0,0,0,1),'F':(.12,.2,0,.35),
    'V':(.12,.2,0,.35),'S':(.18,.35,0,0),'T':(.28,.15,0,0),
    'D':(.28,.15,0,0),'L':(.4,.15,0,0),'R':(.3,0,.45,0),
}
class Mouth:
    name='mouth'
    def evaluate(self,c):
        jaw,spread,rounding,closed=VISEMES.get(c.phoneme(),VISEMES['REST'])
        energy=clamp(c.energy()); smile=c.cue('smile')
        return {'jaw.open':clamp(jaw*(.55+.45*energy)),
                'lip.spread':clamp(spread+.2*smile),
                'lip.round':rounding,'lip.close':closed,
                'lip.smile.L':smile,'lip.smile.R':smile*.97,
                'lip.press':clamp(c.cue('resolve')*.4)}
class Breathing:
    name='breathing'
    def evaluate(self,c):
        i=c.performance.identity
        phase=TAU*i.breath_rate*c.t + stable_unit(i.seed,'breath-phase',0)*TAU
        base=(1-math.cos(phase))/2
        speech=clamp(c.energy())
        return {'breath.expand':clamp(base*(1-.45*speech)),
                'breath.inhale':clamp(math.sin(phase)),
                'breath.exhale':clamp(-math.sin(phase))}
class Chest:
    name='chest'
    def evaluate(self,c):
        b=Breathing().evaluate(c)['breath.expand']
        return {'chest.expand':.08*b,'chest.pitch':.025*c.cue('confidence'),
                'chest.turn':.15*(c.cue('turn_left')-c.cue('turn_right'))}
class Shoulders:
    name='shoulders'
    def evaluate(self,c):
        b=Breathing().evaluate(c)['breath.expand']
        return {'shoulder.raise.L':clamp(.08*b+.15*c.cue('shrug')),
                'shoulder.raise.R':clamp(.08*b+.15*c.cue('shrug')),
                'shoulder.roll':.1*c.cue('confidence')}
class Arms:
    name='arms'
    def evaluate(self,c):
        k=c.performance.identity.gesture_scale
        emphasis=c.cue('emphasis')
        return {'arm.gesture.L':clamp(k*emphasis*.7),
                'arm.gesture.R':clamp(k*emphasis),
                'hand.open.L':clamp(.6*emphasis),
                'hand.open.R':clamp(.8*emphasis)}
class Head:
    name='head'
    def evaluate(self,c):
        yaw=1.35*(c.cue('profile_left')-c.cue('profile_right'))+.65*(c.cue('three_quarter_left')-c.cue('three_quarter_right'))
        yaw+=.18*(c.cue('turn_left')-c.cue('turn_right'))
        return {'head.yaw':clamp(yaw,-1.45,1.45),
                'head.pitch':clamp(.15*c.cue('nod')-.12*c.cue('look_up'),-.5,.5),
                'head.roll':clamp(.1*(c.cue('tilt_left')-c.cue('tilt_right')),-.35,.35)}
class Body:
    name='body'
    def evaluate(self,c):
        yaw=Head().evaluate(c)['head.yaw']
        return {'body.yaw':yaw*.55,'body.weight_shift':.08*(c.cue('shift_left')-c.cue('shift_right'))}
class Hair:
    name='hair'
    def evaluate(self,c):
        # Stateless delayed response from analytic head yaw derivative.
        dt=.025
        p=c.performance
        yp=Head().evaluate(Context(p,min(p.duration,c.t+dt)))['head.yaw']
        ym=Head().evaluate(Context(p,max(0,c.t-dt)))['head.yaw']
        speed=(yp-ym)/(2*dt)
        sway=p.identity.hair_sway
        return {'hair.lag':clamp(-speed*sway,-.4,.4),
                'hair.idle':sway*.025*math.sin(TAU*.37*c.t+stable_unit(p.identity.seed,'hair',0)*TAU)}

MODULES=(Eyes(),Brows(),Cheeks(),Mouth(),Breathing(),Chest(),Shoulders(),Arms(),Head(),Body(),Hair())
LIMITS={'head.yaw':(-1.45,1.45),'head.pitch':(-.5,.5),'head.roll':(-.35,.35),
        'body.yaw':(-.8,.8),'eye.gaze_x':(-1,1),'eye.gaze_y':(-1,1)}
SIGNED=('chest.turn','body.weight_shift','hair.lag','hair.idle')  # signed motion, bounded -1..1
LIMITS.update({k:(-1,1) for k in SIGNED if k not in LIMITS})
def evaluate(p:Performance,t:float)->dict[str,float]:
    if not 0<=t<=p.duration:raise ValueError('time outside performance')
    c=Context(p,t); out={}
    for module in MODULES:
        for key,value in module.evaluate(c).items():
            if key in out:raise ValueError(f'duplicate channel {key}')
            lo,hi=LIMITS.get(key,(0,1))
            out[key]=round(clamp(value,lo,hi),6)
    return out

def frames(p:Performance,fps=30):
    count=int(p.duration*fps+1e-9)  # never sample past the end
    return [{'frame':f,'time':round(f/fps,6),'channels':evaluate(p,f/fps)} for f in range(count+1)]

def demo():
    p=Performance(duration=6.0,cues=(
        Cue(.4,1.4,'attention',.8),Cue(1.0,2.3,'emphasis',.8),
        Cue(2.0,3.4,'smile',.5),Cue(3.2,4.5,'three_quarter_left',1),
        Cue(4.4,5.7,'profile_left',1),Cue(5.0,5.9,'nod',.5)),
        phonemes=(Phoneme(.5,.8,'M'),Phoneme(.8,1.2,'AA'),Phoneme(1.2,1.5,'S'),
                  Phoneme(1.5,1.8,'T'),Phoneme(1.8,2.1,'OW')),
        speech_energy=((0,0),(.5,.4),(1.2,.8),(2.2,.1),(6,0)))
    return p

if __name__=='__main__':
    print(json.dumps(frames(demo(),fps=30),indent=2))
