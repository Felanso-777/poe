import VerificationForm from "../components/VerificationForm";
import ConnectionStatus from "../components/ConnectionStatus";

export default function Verify() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Verify a session</h1>
        <p className="mt-2 text-slate-600">
          Confirm that a session&apos;s Merkle root matches the immutable on-chain record. This proves the data is unchanged,
          not who produced it.
        </p>
      </header>
      <VerificationForm />
      <ConnectionStatus />
    </div>
  );
}
