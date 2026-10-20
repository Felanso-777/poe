# Proof of Effort — React Dashboard (Phase 6)

A responsive React dashboard for the **AuditLedger** smart contract, built with
React, [ethers.js v6](https://docs.ethers.org/), [Vite](https://vitejs.dev/),
and [Tailwind CSS](https://tailwindcss.com/).

It connects to your locally deployed Hardhat contract and displays real
on-chain session records — no fabricated data, no hardcoded verification
results, and no private keys in the frontend.

## Folder structure

```
frontend/
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── .env.example          # copy to .env and configure
├── .gitignore
├── README.md
└── src/
    ├── main.jsx          # React entry point
    ├── index.css         # Tailwind base styles
    ├── App.jsx           # BrowserRouter + BlockchainProvider
    ├── config.js         # env config (RPC, contract address, chain id, demo)
    ├── abi.js            # AuditLedger contract ABI (from Hardhat artifact)
    ├── context/
    │   ├── BlockchainService.js   # ethers.js provider, contract, read helpers, event listener
    │   └── BlockchainContext.jsx  # React context wrapping the service
    ├── components/
    │   ├── Navbar.jsx
    │   ├── ConnectionStatus.jsx
    │   ├── SessionCard.jsx
    │   ├── SessionHistory.jsx
    │   ├── VerificationForm.jsx
    │   ├── EmptyState.jsx
    │   ├── LoadingSpinner.jsx
    │   └── ErrorMessage.jsx
    └── pages/
        ├── Overview.jsx
        ├── SessionHistory.jsx
        ├── SessionDetails.jsx
        └── Verify.jsx
```

## Prerequisites

1. **Node.js** (v18+) and **npm** installed.
2. The Hardhat node running locally:
   ```bash
   cd blockchain
   npx hardhat node
   ```
   This starts a JSON-RPC node on `http://127.0.0.1:8545` (chain id 31337).
3. The `AuditLedger` contract deployed to that node:
   ```bash
   # in a separate terminal, from the blockchain folder
   npx hardhat run scripts/deploy.js --network localhost
   ```
   Copy the printed contract address.

## Install & run the frontend

From the repository root:

```bash
# 1. Install frontend dependencies
cd frontend
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env and set VITE_POE_CONTRACT_ADDRESS to the deployed contract address
# (VITE_POE_RPC_URL and VITE_POE_CHAIN_ID already match the local Hardhat node)

# 3. Start the dev server
npm run dev   # opens http://localhost:5173
```

### Demo mode (no blockchain required)

To try the dashboard with clearly-labeled mock data (no contract deployment needed):

```bash
cp .env.example .env
# Set VITE_DEMO_MODE=true in .env
npm run dev
```

Demo mode shows simulated sessions and a simulated verification result. A
yellow **DEMO MODE** banner is displayed so mock data is never mistaken for
real on-chain records.

## What the dashboard shows

| Page | Purpose |
|------|---------|
| `/` (Overview) | Total session count, verified count, recent activity, connection status |
| `/history` | Session history table: session id, timestamp, effort score, verification status, transaction hash; listens for new `SessionRecorded` events |
| `/sessions/:id` | Session details: Merkle root, blockchain record fields (submitter, timestamp), and a verify form |
| `/verify` | Standalone session verification: enter session id + Merkle root, get a clear success/failure message; also includes report hash file upload verification |

## Report hash verification

The dashboard now includes a **Report Hash Verifier** (on the `/verify` page and inside each session's details page) that lets you upload your local `-report.json` file. The browser computes the SHA-256 hash of the uploaded file using the Web Crypto API and compares it to the `reportHash` stored on-chain by the Python pipeline.

This closes the tampering loophole: if a user edits their local summary report (score, grade, notes) after submission, the recomputed hash will not match the on-chain value and verification will fail with a clear error message.

No file contents are ever sent to a server — the hash is computed entirely in the browser.

## Technical notes

- **Contract connection**: Uses `ethers.JsonRpcProvider` (read-only). No private
  keys are read or stored by the frontend. The signing/submission side remains
  in the Python pipeline (`log_effort.py`).
- **Encoding**: Session ids are hashed client-side with
  `ethers.keccak256(ethers.toUtf8Bytes(uuid))` to match the Python pipeline
  and Solidity `keccak256` of the UTF-8 UUID string.
- **Events**: The dashboard listens for `SessionRecorded` events so new
  sessions appear in real time without a page reload.
- **Verification**: Calls the contract's `verifyMerkleRoot(sessionId, root)`
  view function and displays a clear success or failure message.
- **Demo mode**: Only active when `VITE_DEMO_MODE=true`; labeled clearly on
  every page. Never used unless explicitly enabled.

## Production build

```bash
npm run build    # output in frontend/dist
npm run preview  # serve the production build locally
```

## Troubleshooting

- **"Contract address not configured"**: Make sure you copied `.env.example` to
  `.env` and set `VITE_POE_CONTRACT_ADDRESS` to the deployed address, then
  restart the dev server.
- **"Cannot connect to Ethereum node"**: Ensure `npx hardhat node` is running
  on `http://127.0.0.1:8545`.
- **Empty session list**: Submit a session first via
  `python log_effort.py` (from the repository root), then refresh the page.
