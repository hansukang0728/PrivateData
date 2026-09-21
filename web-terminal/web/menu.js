let el = null;

export function closeMenu() { if (el) { el.remove(); el = null; } }
document.addEventListener("click", closeMenu);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeMenu(); });

// items: {t, i?, k?, act?, sub?, sep?, cap?, dis?, hot?, dot?}
export function showMenu(x, y, items) {
  closeMenu();
  el = document.createElement("div");
  el.className = "menu";
  el.innerHTML = items.map(render).join("");
  document.body.appendChild(el);
  const r = el.getBoundingClientRect();
  el.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 8)) + "px";
  el.style.top  = Math.max(4, Math.min(y, innerHeight - r.height - 8)) + "px";
  el.addEventListener("click", ev => {
    const mi = ev.target.closest(".mi");
    if (!mi || !mi.dataset.idx) return;
    ev.stopPropagation();
    const [a, b] = mi.dataset.idx.split(":").map(Number);
    const it = b >= 0 ? items[a].sub[b] : items[a];
    closeMenu();
    it.act?.();
  });
  return el;

  function render(it, idx) {
    if (it.sep) return '<div class="sep"></div>';
    if (it.cap) return `<div class="cap">${it.cap}</div>`;
    const sub = it.sub
      ? `<div class="menu sub">${it.sub.map((s, j) =>
          `<div class="mi ${s.dot ? "sw" : ""}" data-idx="${idx}:${j}">${
            s.dot ? `<span class="dot" style="background:${s.dot}"></span>` : '<span class="ic"></span>'
          }${s.t}</div>`).join("")}</div>`
      : "";
    return `<div class="mi ${it.dis ? "dis" : ""} ${it.hot ? "hot" : ""} ${it.dot ? "sw" : ""}" ${it.sub ? "" : `data-idx="${idx}:-1"`}>
      ${it.dot ? `<span class="dot" style="background:${it.dot}"></span>` : `<span class="ic">${it.i || ""}</span>`}
      ${it.t}<span class="k">${it.sub ? "&#9654;" : (it.k || "")}</span>${sub}</div>`;
  }
}

let toastEl = null;
export function toast(msg) {
  toastEl?.remove();
  toastEl = document.createElement("div");
  toastEl.className = "toast";
  toastEl.textContent = msg;
  document.body.appendChild(toastEl);
  const mine = toastEl;
  setTimeout(() => { if (mine === toastEl) { mine.remove(); toastEl = null; } }, 3000);
}
