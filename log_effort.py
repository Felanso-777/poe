import hashlib
import json
import os
from web3 import Web3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_rel_path=".secrets/config.json"):
  config_path = os.path.join(BASE_DIR, config_rel_path)
  if not os.path.exists(config_path):
    config_path = os.path.join(BASE_DIR, "secrets/config.json")
  with open(config_path, "r") as f:
    return json.load(f)


def calculate_file_hash(filepath):
  abs_filepath = (
      filepath
      if os.path.isabs(filepath)
      else os.path.join(BASE_DIR, filepath)
  )
  hasher = hashlib.sha256()
  with open(abs_filepath, "rb") as f:
    while chunk := f.read(8192):
      hasher.update(chunk)
  return hasher.hexdigest()


def log_hash_to_chain():
  """Logs the current report hash onto the blockchain ledger."""
  config = load_config()
  w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
  assert w3.is_connected(), "RPC connection failed"

  artifact_path = os.path.join(
      BASE_DIR, "artifacts/contracts/AuditLedger.sol/AuditLedger.json"
  )
  with open(artifact_path, "r") as f:
    abi = json.load(f)["abi"]

  contract = w3.eth.contract(
      address=Web3.to_checksum_address(config["contract_address"]), abi=abi
  )
  file_hash = calculate_file_hash(config["report_path"])

  print(f"Submitting hash to blockchain: {file_hash}")
  tx_hash = contract.functions.setHash(file_hash).transact(
      {"from": w3.eth.accounts[0]}
  )
  receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
  print(f"✅ Mined in block #{receipt.blockNumber}")
  return file_hash