import sys
from log_effort import log_hash_to_chain
from verify_effort import verify


def run_pipeline():
  print("=" * 55)
  print("🚀 STARTING PROOF-OF-EFFORT (PoE) AUDIT PIPELINE")
  print("=" * 55)

  # Step 1: Run verification check
  print("\n[Step 1/2] Checking blockchain baseline integrity...")
  verification_status = verify()

  # Step 2: Decide whether to log or abort
  print("\n[Step 2/2] Processing pipeline decisions...")

  if verification_status is None:
    # Genesis run: No hash has been written yet
    print("ℹ️ Genesis State detected. Writing initial baseline to ledger...")
    tx_hash = log_hash_to_chain()
    print(f"🎉 Initial baseline established successfully: {tx_hash}")

  elif verification_status is True:
    # Verified run: Current state matches the ledger
    print("✅ Verification passed! Logging updated session to blockchain...")
    tx_hash = log_hash_to_chain()
    print(f"🎉 New session logged successfully: {tx_hash}")

  else:
    # Tamper run: Verification failed
    print("❌ PIPELINE ABORTED: Security alert triggered!")
    print("🚨 Cannot commit new changes until tampering is resolved.")
    sys.exit(1)

  print("\n" + "=" * 55)
  print("✨ PIPELINE FINISHED")
  print("=" * 55)


if __name__ == "__main__":
  run_pipeline()