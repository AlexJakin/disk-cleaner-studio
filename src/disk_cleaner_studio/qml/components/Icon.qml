import QtQuick

Canvas {
    id: icon
    property string name: "grid"
    property color ink: "#5b7675"
    implicitWidth: 20
    implicitHeight: 20
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d"); c.reset(); c.scale(width / 24, height / 24);
        c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 1.7; c.lineCap = "round"; c.lineJoin = "round";
        function line(points) { c.beginPath(); c.moveTo(points[0][0], points[0][1]); for (var i = 1; i < points.length; i++) c.lineTo(points[i][0], points[i][1]); c.stroke(); }
        function box(x,y,w,h) { c.strokeRect(x,y,w,h); }
        if (name === "explore" || name === "grid") { box(3,3,9,11); box(15,3,6,6); box(15,12,6,9); box(3,17,9,4); }
        else if (name === "spark") { line([[12,2],[14.5,9.5],[22,12],[14.5,14.5],[12,22],[9.5,14.5],[2,12],[9.5,9.5],[12,2]]); }
        else if (name === "history") { c.beginPath(); c.arc(12,12,8,Math.PI*1.15,Math.PI*2.95); c.stroke(); line([[3,4],[3,9],[8,9]]); line([[12,7],[12,12],[16,14]]); }
        else if (name === "backup") { line([[4,8],[4,21],[20,21],[20,8]]); box(3,3,18,5); line([[9,12],[15,12]]); }
        else if (name === "settings") { c.beginPath(); c.arc(12,12,3,0,Math.PI*2); c.stroke(); c.beginPath(); c.arc(12,12,8,0,Math.PI*2); c.stroke(); for(var j=0;j<8;j++){ var a=j*Math.PI/4; line([[12+8*Math.cos(a),12+8*Math.sin(a)],[12+10*Math.cos(a),12+10*Math.sin(a)]]); } }
        else if (name === "scan") { line([[3,8],[3,3],[8,3]]); line([[16,3],[21,3],[21,8]]); line([[21,16],[21,21],[16,21]]); line([[8,21],[3,21],[3,16]]); line([[6,12],[18,12]]); }
        else if (name === "import") { line([[4,14],[4,21],[20,21],[20,14]]); line([[12,3],[12,15]]); line([[7,10],[12,15],[17,10]]); }
        else if (name === "folder") { line([[3,7],[3,20],[21,20],[21,7],[12,7],[10,4],[3,4],[3,7]]); }
        else if (name === "file") { line([[5,3],[14,3],[19,8],[19,21],[5,21],[5,3]]); line([[14,3],[14,8],[19,8]]); line([[8,13],[16,13]]); line([[8,17],[14,17]]); }
        else if (name === "up") { line([[6,12],[12,6],[18,12]]); line([[12,6],[12,21]]); }
        else if (name === "chevron") { line([[9,5],[16,12],[9,19]]); }
        else if (name === "close") { line([[6,6],[18,18]]); line([[18,6],[6,18]]); }
        else if (name === "check") { line([[4,12],[9,17],[20,6]]); }
        else if (name === "info") { c.beginPath(); c.arc(12,12,9,0,Math.PI*2); c.stroke(); line([[12,11],[12,17]]); c.fillRect(11.2,6.5,1.6,1.6); }
        else if (name === "shield") { line([[12,2],[21,6],[20,14],[17,19],[12,22],[7,19],[4,14],[3,6],[12,2]]); line([[8,12],[11,15],[16,9]]); }
        else if (name === "disk") { box(3,5,18,14); line([[3,13],[21,13]]); c.fillRect(16,15.5,2,1.8); }
        else if (name === "external") { line([[13,3],[21,3],[21,11]]); line([[21,3],[10,14]]); line([[9,5],[4,5],[4,21],[19,21],[19,15]]); }
        else if (name === "refresh") { c.beginPath(); c.arc(12,12,8,Math.PI*.3,Math.PI*1.9); c.stroke(); line([[21,4],[21,9],[16,9]]); }
    }
}
