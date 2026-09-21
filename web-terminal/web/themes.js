export const THEMES = {
  tokyonight:{n:"Tokyo Night", bg:"#1A1B26",fg:"#A9B1D6",dim:"#565F89",chrome:"#16161E",panel:"#1A1B26",line:"#2A2E42",acc:"#7AA2F7",red:"#F7768E",green:"#9ECE6A",yellow:"#E0AF68",blue:"#7AA2F7",magenta:"#BB9AF7",cyan:"#7DCFFF"},
  campbell:{n:"Campbell (PowerShell 기본)", bg:"#0C0C0C",fg:"#CCCCCC",dim:"#767676",chrome:"#1A1A1A",panel:"#101010",line:"#2E2E2E",acc:"#3A96DD",red:"#E74856",green:"#16C60C",yellow:"#F9F1A5",blue:"#3B78FF",magenta:"#B4009E",cyan:"#61D6D6"},
  onehalf:{n:"One Half Dark", bg:"#282C34",fg:"#DCDFE4",dim:"#6B717D",chrome:"#21252B",panel:"#242830",line:"#3A3F4B",acc:"#61AFEF",red:"#E06C75",green:"#98C379",yellow:"#E5C07B",blue:"#61AFEF",magenta:"#C678DD",cyan:"#56B6C2"},
  dracula:{n:"Dracula", bg:"#282A36",fg:"#F8F8F2",dim:"#6272A4",chrome:"#21222C",panel:"#242530",line:"#3B3E52",acc:"#BD93F9",red:"#FF5555",green:"#50FA7B",yellow:"#F1FA8C",blue:"#8BE9FD",magenta:"#FF79C6",cyan:"#8BE9FD"},
  nord:{n:"Nord", bg:"#2E3440",fg:"#D8DEE9",dim:"#68738A",chrome:"#272C36",panel:"#2B303B",line:"#3B4252",acc:"#88C0D0",red:"#BF616A",green:"#A3BE8C",yellow:"#EBCB8B",blue:"#81A1C1",magenta:"#B48EAD",cyan:"#88C0D0"},
  gruvbox:{n:"Gruvbox Dark", bg:"#282828",fg:"#EBDBB2",dim:"#928374",chrome:"#1D2021",panel:"#232323",line:"#3C3836",acc:"#FE8019",red:"#FB4934",green:"#B8BB26",yellow:"#FABD2F",blue:"#83A598",magenta:"#D3869B",cyan:"#8EC07C"},
  rosepine:{n:"Rosé Pine", bg:"#191724",fg:"#E0DEF4",dim:"#6E6A86",chrome:"#14121F",panel:"#1B1930",line:"#2A273F",acc:"#EBBCBA",red:"#EB6F92",green:"#31748F",yellow:"#F6C177",blue:"#9CCFD8",magenta:"#C4A7E7",cyan:"#9CCFD8"},
  solarized:{n:"Solarized Light", bg:"#FDF6E3",fg:"#586E75",dim:"#93A1A1",chrome:"#EEE8D5",panel:"#F5EFDC",line:"#DDD6C1",acc:"#268BD2",red:"#DC322F",green:"#859900",yellow:"#B58900",blue:"#268BD2",magenta:"#D33682",cyan:"#2AA198"}
};

const VARS = ["bg","fg","dim","chrome","panel","line","acc","red","green","yellow","blue","magenta","cyan"];

export function applyTheme(appEl, key) {
  const t = THEMES[key] || THEMES.tokyonight;
  // 메뉴·토스트는 .app 밖(body 바로 아래)에 붙으므로 :root 에도 같은 값을 꽂아야 한다
  VARS.forEach(v => {
    appEl.style.setProperty("--" + v, t[v]);
    document.documentElement.style.setProperty("--" + v, t[v]);
  });
  document.body.style.background = t.bg;
  document.body.style.color = t.fg;
  return xtermTheme(t);
}

// 같은 토큰을 xterm 팔레트로 옮긴다 — UI 크롬과 터미널이 한 덩어리로 보이도록
export function xtermTheme(t) {
  return {
    background: t.bg, foreground: t.fg, cursor: t.acc, cursorAccent: t.bg,
    selectionBackground: t.acc + "55",
    black: t.chrome, red: t.red, green: t.green, yellow: t.yellow,
    blue: t.blue, magenta: t.magenta, cyan: t.cyan, white: t.fg,
    brightBlack: t.dim, brightRed: t.red, brightGreen: t.green, brightYellow: t.yellow,
    brightBlue: t.blue, brightMagenta: t.magenta, brightCyan: t.cyan, brightWhite: "#ffffff"
  };
}
