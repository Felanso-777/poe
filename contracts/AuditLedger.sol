// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract AuditLedger {
    // Stores the file hash permanently on the blockchain
    string public storedHash;

    // Writes or updates the stored hash
    function setHash(string memory _newHash) public {
        storedHash = _newHash;
    }

    // Verifies whether an incoming hash matches the stored hash
    function verifyHash(string memory _claimedHash) public view returns (bool) {
        // In Solidity, strings cannot be compared directly with '=='
        // We compare their keccak256 cryptographic hashes instead
        return keccak256(abi.encodePacked(_claimedHash)) == keccak256(abi.encodePacked(storedHash));
    }
}