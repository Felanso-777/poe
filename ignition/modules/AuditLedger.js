const { buildModule } = require("@nomicfoundation/hardhat-ignition/modules");

module.exports = buildModule("AuditLedgerModule", (m) => {
  const auditLedger = m.contract("AuditLedger");

  return { auditLedger };
});