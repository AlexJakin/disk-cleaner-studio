.pragma library

// Binary partition keeps every sibling visible without inventing or adding sizes.
function layout(source, width, height) {
    if (!source || width <= 0 || height <= 0) return [];
    var items = [];
    for (var i = 0; i < source.length; i++) {
        var size = Number(source[i].size || 0);
        if (size > 0) items.push({data:source[i], weight:size, rank:i});
    }
    items.sort(function(a,b){ return b.weight - a.weight; });
    var out = [];
    function split(part, x,y,w,h) {
        if (!part.length) return;
        if (part.length === 1) { out.push({x:x,y:y,w:w,h:h,data:part[0].data,rank:part[0].rank}); return; }
        var total=0; for (var j=0;j<part.length;j++) total+=part[j].weight;
        var acc=part[0].weight, n=1;
        while (n<part.length-1 && Math.abs(total/2-(acc+part[n].weight)) < Math.abs(total/2-acc)) { acc+=part[n].weight; n++; }
        var ratio=acc/total;
        if(w>=h) { split(part.slice(0,n),x,y,w*ratio,h); split(part.slice(n),x+w*ratio,y,w*(1-ratio),h); }
        else { split(part.slice(0,n),x,y,w,h*ratio); split(part.slice(n),x,y+h*ratio,w,h*(1-ratio)); }
    }
    split(items,0,0,width,height);
    return out;
}
