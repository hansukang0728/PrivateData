async function call(url, opts) {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  const body = await res.json().catch(() => ({ ok: false, error: "응답을 읽지 못했습니다" }));
  if (!res.ok || body.ok === false) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}
const post = (url, data) => call(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
});

export const api = {
  env:       ()               => call("/api/env"),
  drives:    ()               => call("/api/fs/drives"),
  list:      p                => call("/api/fs/list?path=" + encodeURIComponent(p)),
  mkdir:     (dir, name)      => post("/api/fs/mkdir", { dir, name }),
  newFile:   (dir, name)      => post("/api/fs/newfile", { dir, name }),
  rename:    (from, to)       => post("/api/fs/rename", { from, to }),
  remove:    (path, perm)     => post("/api/fs/delete", { path, permanent: !!perm }),
  transfer:  (sources, dest, move) => post("/api/fs/transfer", { sources, dest, move }),
  open:      path             => post("/api/shell/open", { path }),
  reveal:    path             => post("/api/shell/reveal", { path }),
  properties:path             => post("/api/shell/properties", { path }),
  loadWs:    ()               => call("/api/workspace"),
  saveWs:    state            => post("/api/workspace", state)
};
