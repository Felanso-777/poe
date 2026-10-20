export default function LoadingSpinner({ message = "Loading…" }) {
  return (
    <div role="status" className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-poe-600" />
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  );
}
