"""Availability is estimated only within the validity window of each observation."""
from collections import defaultdict

def aggregate(cameras, observations, start, end, buckets=12):
    duration=end-start
    width=duration/buckets
    timeline=[{'start':int(start+i*width),'end':int(start+(i+1)*width),'online_seconds':0.0,'offline_seconds':0.0} for i in range(buckets)]
    groups=defaultdict(list)
    for sample in observations:groups[sample['camera_id']].append(sample)
    rows=[]
    for camera in cameras:
        samples=sorted(groups[camera['id']],key=lambda s:(s['timestamp'],s['id']))
        online=offline=0.0;episodes=0;previous=None;previous_end=None
        for i,sample in enumerate(samples):
            left=max(start,sample['timestamp'])
            right=min(end,sample['valid_until'],samples[i+1]['timestamp'] if i+1<len(samples) else end)
            if right<=left or sample['status'] not in ['online','offline']:continue
            span=right-left
            if sample['status']=='online':online+=span
            else:
                offline+=span
                if previous!='offline' or previous_end!=left:episodes+=1
            previous=sample['status'];previous_end=right
            first=max(0,min(buckets-1,int((left-start)/width)))
            last=max(0,min(buckets-1,int((right-start-0.000001)/width)))
            for b in range(first,last+1):
                amount=max(0,min(right,start+(b+1)*width)-max(left,start+b*width))
                timeline[b][sample['status']+'_seconds']+=amount
        known=online+offline
        rows.append(camera|{'online_seconds':round(online,2),'offline_seconds':round(offline,2),'unknown_seconds':round(max(0,duration-known),2),'availability':round(100*online/known,2) if known else None,'coverage':round(100*known/duration,2),'offline_episodes':episodes})
    total=duration*len(cameras)
    online=sum(r['online_seconds'] for r in rows);offline=sum(r['offline_seconds'] for r in rows);known=online+offline
    for b in timeline:
        possible=width*len(cameras)
        b['unknown_seconds']=round(max(0,possible-b['online_seconds']-b['offline_seconds']),2)
        b['online_seconds']=round(b['online_seconds'],2);b['offline_seconds']=round(b['offline_seconds'],2)
        b['online_percent']=round(100*b['online_seconds']/possible,2) if possible else 0
        b['offline_percent']=round(100*b['offline_seconds']/possible,2) if possible else 0
        b['unknown_percent']=round(100*b['unknown_seconds']/possible,2) if possible else 0
    return {'start':start,'end':end,'camera_count':len(cameras),'online_seconds':round(online,2),'offline_seconds':round(offline,2),'unknown_seconds':round(max(0,total-known),2),'availability':round(100*online/known,2) if known else None,'coverage':round(100*known/total,2) if total else 0,'offline_episodes':sum(r['offline_episodes'] for r in rows),'rows':rows,'timeline':timeline}


def compact_observations(samples,start,end):
    """Consume camera/time ordered rows, retaining transitions and coverage gaps."""
    result=[];previous=None
    def emit(sample,next_time):
        left=max(start,sample['timestamp']);right=min(end,sample['valid_until'],next_time)
        if right<=left or sample['status'] not in ('online','offline'):return
        if result and result[-1]['camera_id']==sample['camera_id'] and result[-1]['status']==sample['status'] and result[-1]['valid_until']==left:
            result[-1]['valid_until']=right
        else:result.append(sample|{'timestamp':left,'valid_until':right})
    for sample in samples:
        if previous:emit(previous,sample['timestamp'] if previous['camera_id']==sample['camera_id'] else end)
        previous=sample
    if previous:emit(previous,end)
    return result
