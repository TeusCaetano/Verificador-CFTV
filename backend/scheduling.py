from collections import Counter

def select_ready(rows,due,busy,now,workers,per_recorder):
    """No queued executor tasks; honor NVR limits and oldest deadlines/checks."""
    hosts={id:host for id,host,checked in rows}
    occupied=Counter(hosts[id] for id in busy if id in hosts)
    capacity=max(0,workers-len(busy));chosen=[]
    candidates=sorted((row for row in rows if row[0] not in busy and due.get(row[0],0)<=now),key=lambda row:(due.get(row[0],0),row[2],row[0]))
    for id,host,checked in candidates:
        if occupied[host]>=per_recorder:continue
        chosen.append(id);occupied[host]+=1
        if len(chosen)>=capacity:break
    return chosen if capacity else []
