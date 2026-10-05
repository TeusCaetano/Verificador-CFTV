'use strict';
// Connected groups of pins whose projected positions are within radius pixels.
// Spatial buckets avoid checking every pair for a large inventory.
function groupCameraPoints(points,radius=58){
 const identical=new Map();for(const p of points){const key=p.x+","+p.y;if(!identical.has(key))identical.set(key,[]);identical.get(key).push(p);}points=[...identical.values()].map(group=>group[0]);
 const parent=points.map((_,i)=>i),rank=points.map(()=>0),buckets=new Map();
 function root(i){while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;}
 function union(a,b){a=root(a);b=root(b);if(a===b)return;if(rank[a]<rank[b])[a,b]=[b,a];parent[b]=a;if(rank[a]===rank[b])rank[a]++;}
 points.forEach((p,i)=>{const gx=Math.floor(p.x/radius),gy=Math.floor(p.y/radius);for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++)for(const j of buckets.get((gx+dx)+','+(gy+dy))||[]){const q=points[j];if((p.x-q.x)**2+(p.y-q.y)**2<=radius**2)union(i,j);}const key=gx+','+gy;if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(i);});
 const groups=new Map();points.forEach((p,i)=>{const k=root(i);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(...identical.get(p.x+","+p.y));});return [...groups.values()];
}
if(typeof module!=='undefined')module.exports={groupCameraPoints};
