import hashlib
import json
import os
import sys
from web3 import Web3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_rel_path=".secrets/config.json"):
  """Load network and contract configuration."""
  config_path = os.path.join(BASE_DIR, config_rel_path)
  if not os.path.exists(config_path):
    alt_path = os.path.join(BASE_DIR, "secrets/config.json")
    if os.path.exists(alt_path):
      config_path = alt_path
    else:
      raise FileNotFoundError(f"Config file not found: {config_path}")

  with open(config_path, "r") as f:
    return json.load(f)


def calculate_file_hash(filepath):
  """Compute the SHA-256 hash of the target session report."""
  abs_filepath = (
      filepath
      if os.path.isabs(filepath)
      else os.path.join(BASE_DIR, filepath)
  )
  if not os.path.exists(abs_filepath):
    raise FileNotFoundError(f"Report file not found: {abs_filepath}")

  hasher = hashlib.sha256()
  with open(abs_filepath, "rb") as f:
    while chunk := f.read(8192):
      hasher.update(chunk)
  return hasher.hexdigest()


def verify():
  """Verifies local file integrity against the on-chain baseline.

  Returns:
      None  : Genesis / empty baseline (no record on-chain yet)
      True  : Integrity verified (local hash matches ledger)
      False : Tampering detected (hash mismatch)
  """
  # 1. Connect to RPC provider
  config = load_config()
  w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
  if not w3.is_connected():
    print(f"❌ Error: Cannot connect to node at {config['rpc_url']}")
    sys.exit(1)

  # 2. Load ABI and Contract instance
  artifact_path = os.path.join(
      BASE_DIR, "artifacts/contracts/AuditLedger.sol/AuditLedger.json"
  )
  with open(artifact_path, "r") as f:
    abi = json.load(f)["abi"]

  contract = w3.eth.contract(
      address=Web3.to_checksum_address(config["contract_address"]), abi=abi
  )

  # 3. Read current stored baseline (zero gas cost view call)
  stored_hash = contract.functions.storedHash().call()

  # Check if contract is in Genesis / uninitialized state
  is_empty = (
      not stored_hash
      or stored_hash == ""
      or stored_hash.replace("0x", "") == "0" * 64
  )

  if is_empty:
    print("⚠️ Blockchain has no stored baseline hash yet (Genesis state).")
    return None

  # 4. Hash the local file
  local_hash = calculate_file_hash(config["report_path"])

  print(f"📁 Local file hash   : {local_hash}")
  print(f"⛓️ On-chain baseline  : {stored_hash}")

  # 5. Verify match via contract view function
  is_valid = contract.functions.verifyHash(local_hash).call()

  print("-" * 50)
  if is_valid:
    print("✅ INTEGRITY OK: Local file matches the on-chain record.")
    return True
  else:
    print(
        "🚨 TAMPERING DETECTED: Local file hash differs from blockchain"
        " record!"
    )
    return False


if __name__ == "__main__":
  verify()