/** Small colour strip derived from a hash/id so each record is recognisable at a glance. */
export default function Fingerprint({ value = "", cells = 8, big = false, className = "" }) {
  const s = String(value) || "x";
  return (
    <span aria-hidden="true" className={`inline-flex shrink-0 overflow-hidden rounded-md ${className}`}>
      {Array.from({ length: cells }, (_, i) => {
        const n = (s.charCodeAt((i * 7) % s.length) * 31 + s.charCodeAt((i * 7 + 3) % s.length) * 17 + i * 53) % 256;
        return (
          <i
            key={i}
            className={`block ${big ? "h-8 w-2.5" : "h-5 w-1.5"}`}
            style={{ background: `hsl(${(190 + Math.round((n / 255) * 170)) % 360} 60% ${40 + (n % 5) * 6}%)` }}
          />
        );
      })}
    </span>
  );
}
