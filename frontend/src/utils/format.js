export const short = (s, a = 6, b = 4) =>
  !s ? "—" : s.length <= a + b + 1 ? s : `${s.slice(0, a)}…${s.slice(-b)}`;

export const when = (t) => (t ? new Date(t).toLocaleString() : "—");
