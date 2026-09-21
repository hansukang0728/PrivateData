// 로컬 터미널을 여는 서버다. 아래 셋은 타협하지 않는다.
//   1) 127.0.0.1 에만 바인딩   2) 1회용 토큰   3) WebSocket Origin 검사
import crypto from "node:crypto";

export const TOKEN = crypto.randomBytes(24).toString("hex");
export const COOKIE = "poshdeck_token";

function cookieToken(req) {
  const raw = req.headers.cookie;
  if (!raw) return null;
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() === COOKIE) return decodeURIComponent(part.slice(i + 1).trim());
  }
  return null;
}

export function tokenOf(req) {
  const url = new URL(req.url, "http://127.0.0.1");
  return url.searchParams.get("token") || cookieToken(req);
}

function sameToken(given) {
  if (!given || given.length !== TOKEN.length) return false;
  return crypto.timingSafeEqual(Buffer.from(given), Buffer.from(TOKEN));
}

// 첫 방문은 ?token= 으로 들어온다. 맞으면 쿠키로 굳히고 쿼리 없는 주소로 보낸다.
export function gate(port) {
  const allowedOrigins = new Set([`http://127.0.0.1:${port}`, `http://localhost:${port}`]);

  return function (req, res, next) {
    const given = tokenOf(req);
    if (!sameToken(given)) {
      res.status(401).type("html").send(
        "<h1>401</h1><p>토큰이 없거나 맞지 않습니다. 서버를 띄운 창에 찍힌 주소로 다시 들어오세요.</p>"
      );
      return;
    }
    // 쓰기 요청은 브라우저가 보낸 Origin 이 우리 자신인지까지 본다 (CSRF 차단)
    if (req.method !== "GET" && req.headers.origin && !allowedOrigins.has(req.headers.origin)) {
      res.status(403).json({ error: "origin_rejected" });
      return;
    }
    if (new URL(req.url, "http://127.0.0.1").searchParams.has("token")) {
      res.cookie?.(COOKIE, TOKEN, { httpOnly: true, sameSite: "strict", path: "/" });
      res.setHeader("Set-Cookie", `${COOKIE}=${TOKEN}; HttpOnly; SameSite=Strict; Path=/`);
      if (req.path === "/") { res.redirect("/"); return; }
    }
    next();
  };
}

export function checkUpgrade(req, port) {
  const origin = req.headers.origin;
  if (origin && origin !== `http://127.0.0.1:${port}` && origin !== `http://localhost:${port}`) return false;
  return sameToken(tokenOf(req));
}
