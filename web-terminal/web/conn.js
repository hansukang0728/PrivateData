// 서버와의 단일 WebSocket. 끊기면 스스로 다시 붙고, 붙으면 앱이 세션을 다시 잇는다.
let sock = null, ready = false, queue = [], onOpen = null, onStatus = null;
const routes = new Map();

export function connect(handlers) {
  onOpen = handlers.onOpen; onStatus = handlers.onStatus;
  open();
}

function open() {
  const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
  sock = new WebSocket(url);

  sock.onopen = () => {
    ready = true;
    onStatus?.("ok");
    queue.splice(0).forEach(m => sock.send(JSON.stringify(m)));
    onOpen?.();
  };
  sock.onclose = () => {
    ready = false;
    onStatus?.("bad");
    setTimeout(open, 1000);                 // 서버를 다시 띄우면 알아서 붙는다
  };
  sock.onerror = () => { try { sock.close(); } catch {} };
  sock.onmessage = ev => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    const fn = routes.get(m.id);
    if (fn) fn(m);
  };
}

export function send(msg) {
  if (ready && sock.readyState === 1) sock.send(JSON.stringify(msg));
  else queue.push(msg);
}
export function route(id, fn) { routes.set(id, fn); }
export function unroute(id) { routes.delete(id); }
