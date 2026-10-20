# deploy_and_test.ps1 — Start Hardhat node, deploy contract, run pipeline
# Run from: D:\poe_latest\blockchain

# Step 1: Start Hardhat node in background
Write-Output "Starting Hardhat node..."
$node = Start-Process -FilePath "node" -ArgumentList "node_modules/.bin/hardhat", "node" -WorkingDirectory (Get-Location).Path -PassThru
Write-Output "Node PID: $($node.Id)"

# Step 2: Wait for node to be ready
Write-Output "Waiting for node to be ready..."
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:8545" -Method Post -ContentType "application/json" -Body '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' -ErrorAction Stop
        Write-Output "Node is ready (block number: $($response.result))"
        break
    } catch {
        if ($i -eq 29) {
            Write-Error "Node did not become ready in time"
            exit 1
        }
    }
}

# Step 3: Deploy contract
Write-Output "Deploying contract..."
$deployOutput = npx hardhat run scripts/deploy.js --network localhost 2>&1
Write-Output $deployOutput

# Extract contract address
$addressLine = $deployOutput | Select-String "deployed at:"
if ($addressLine) {
    $address = $addressLine.ToString().Split(":")[-1].Trim()
    Write-Output "Contract address: $address"
    
    # Step 4: Update frontend .env
    $envPath = "D:\poe_latest\frontend\.env"
    $envContent = Get-Content $envPath -Raw
    $envContent = $envContent -replace 'VITE_POE_CONTRACT_ADDRESS=.*', "VITE_POE_CONTRACT_ADDRESS=$address"
    Set-Content $envPath $envContent
    Write-Output "Updated frontend/.env with contract address: $address"
} else {
    Write-Error "Could not extract contract address from deploy output"
    exit 1
}

# Step 5: Run Python pipeline
Write-Output "Running Python pipeline..."
Set-Location "D:\poe_latest"
python log_effort.py --duration 5 --batch-size 10 --dry-run --output-dir ./poe-data-collector --seed 42 2>&1

# Step 6: Kill the node
Write-Output "Stopping Hardhat node..."
Stop-Process -Id $node.Id -Force
Write-Output "Done."
