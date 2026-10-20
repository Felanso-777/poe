// scripts/deploy.js
// -----------------
// Deploys AuditLedger to the configured network and prints the contract
// address.  Run with:
//
//   npx hardhat run scripts/deploy.js --network hardhat
//
// For a persistent local node (e.g. npx hardhat node), pass --network localhost
// and set the RPC URL / accounts in hardhat.config.js.

const { ethers } = require("hardhat");

async function main() {
    const [deployer] = await ethers.getSigners();

    console.log("Deploying AuditLedger...");
    console.log("  Deployer :", deployer.address);
    console.log(
        "  Balance  :",
        ethers.formatEther(await ethers.provider.getBalance(deployer.address)),
        "ETH"
    );

    // Deploy
    const AuditLedger = await ethers.getContractFactory("AuditLedger");
    const ledger = await AuditLedger.deploy();
    await ledger.waitForDeployment();

    const address = await ledger.getAddress();
    console.log("\n✅  AuditLedger deployed at:", address);
    console.log(
        "   Owner (authorised by default):",
        await ledger.owner()
    );

    // Verify the deployer is authorised (should always be true)
    const isAuth = await ledger.isAuthorized(deployer.address);
    console.log("   Deployer authorised:", isAuth);
}

main()
    .then(() => process.exit(0))
    .catch((err) => {
        console.error(err);
        process.exit(1);
    });
