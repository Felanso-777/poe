const styles = {
  true: ["Verified", "bg-emerald-50 text-emerald-700", "M5 12l4 4 10-10"],
  false: ["Failed", "bg-rose-50 text-rose-700", "M6 6l12 12M18 6L6 18"],
  null: ["Not checked", "bg-slate-100 text-slate-600", "M6 12h12"],
};

export default function Status({ state, className = "" }) {
  const [label, tone, path] = styles[state === true ? "true" : state === false ? "false" : "null"];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${tone} ${className}`}>
      <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d={path} /></svg>
      {label}
    </span>
  );
}
