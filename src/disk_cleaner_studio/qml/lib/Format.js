.pragma library

function bytes(value) {
    var n = Number(value || 0);
    if (!isFinite(n)) return "—";
    var sign = n < 0 ? "−" : "";
    n = Math.abs(n);
    var units = ["B", "KiB", "MiB", "GiB", "TiB"];
    var i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return sign + (i === 0 ? n.toFixed(0) : n >= 100 ? n.toFixed(1) : n.toFixed(2)) + " " + units[i];
}
function date(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value).replace("T", " ").slice(0, 19);
    function pad(n) { return n < 10 ? "0" + n : String(n); }
    return d.getFullYear() + "/" + pad(d.getMonth()+1) + "/" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}
function risk(value, cleanable) {
    return ({low:"低风险",medium:"中风险",high:"高风险",safe:"低风险",review:"需确认",manual:"仅建议"})[value] || (cleanable ? "需确认" : "仅建议");
}
function list(value) {
    if (!value) return "";
    return typeof value === "string" ? value : value.join("；");
}
function status(value) {
    return ({completed:"完成",complete:"完成",success:"成功",succeeded:"成功",failed:"失败",partial:"部分完成",partial_success:"部分完成",cancelled:"已取消",in_progress:"进行中",verified:"已校验",skipped:"已跳过",restored:"已恢复",deleted:"已清理",ready:"已就绪",invalid:"校验失败",backing_up:"备份中",pending:"待处理",cleaning:"清理中"})[value] || value || "—";
}
