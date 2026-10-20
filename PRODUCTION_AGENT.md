# Proof of Effort production Windows agent

The production agent is the consent-first desktop application in
`agent/windows_app.py`. It is separate from `MockCollector` and the legacy
`poe-data-collector/app.py`.

## Install dependencies

From the repository root:

```powershell
python -m pip install -r requirements.txt
```

## Run from source

Windows 10/11 is required for the production collector:

```powershell
python -m agent.windows_app
```

The application requires at least one folder selected through its folder
picker. Monitoring does not start until the user grants consent. The agent
stores normalized JSONL events under `~/.poe/sessions` by default.

Collected data is limited to:

- file create, modify, delete, and rename metadata inside selected folders
- relative file name, extension, language, and file size
- process names without arguments

It does not store file contents, passwords, secrets, process arguments, raw
keyboard contents, clipboard data, or window text.

## Build an executable

From `D:\poe_latest\agent` on Windows:

```powershell
pyinstaller --clean --noconfirm production-agent.spec
```

The executable is written to `agent\dist\ProofOfEffortMonitor.exe`.

Or use the helper script:

```powershell
.\build_windows.ps1 -InstallDependencies
```

The blockchain is optional for local operation. If configuration or RPC
connectivity is unavailable, the report remains local and the result is added
to `pending-submissions.jsonl`; the UI reports the pending state explicitly.

## End-to-end flow

```text
Folder consent
  -> WindowsCollector
  -> authorized file/process events
  -> append-only JSONL
  -> heuristic + ML analysis
  -> deterministic report/hash/Merkle root
  -> blockchain anchoring or explicit pending queue
  -> frontend verification
```

The ML result is behavioral prediction only. A blockchain match proves
cryptographic integrity of the registered artifact, not human identity or
authorship.
