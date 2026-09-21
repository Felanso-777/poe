const hre = require("hardhat");

async function main() {
  // 1. Fetch the contract factory for AuditLedger
  const AuditLedger = await hre.ethers.getContractFactory("AuditLedger");

  // 2. Deploy the contract to the local node
  console.log("Deploying AuditLedger contract...");
  const auditLedger = await AuditLedger.deploy();

  await auditLedger.waitForDeployment();

  // 3. Print the deployed address
  const contractAddress = await auditLedger.getAddress();
  console.log(`✅ AuditLedger deployed successfully to: ${contractAddress}`);
}

main().catch((error) => {
  console.error("❌ Deployment failed:", error);
  process.exitCode = 1;
});
