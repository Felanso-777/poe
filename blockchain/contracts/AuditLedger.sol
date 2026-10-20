// SPDX-License-Identifier: MIT
pragma solidity ^0.8.27;

/**
 * @title AuditLedger
 * @notice Append-only on-chain registry of developer session proofs for the
 *         Proof of Effort (PoE) system.
 *
 * Design principles
 * -----------------
 * • Privacy-preserving: only stores opaque hashes (sessionId, merkleRoot)
 *   and necessary metadata (submitter address, block timestamp). No raw
 *   activity events, file paths, or source code ever touch this contract.
 *
 * • Immutability: once a session is recorded it can never be overwritten or
 *   deleted. Duplicate sessionIds are rejected.
 *
 * • Least-privilege access: the contract owner manages an authorised-submitter
 *   allowlist. Any account on the list may submit sessions; the owner is
 *   always authorised. This prevents arbitrary writes while still allowing
 *   multiple legitimate developer pipelines.
 */
contract AuditLedger {
    // -------------------------------------------------------------------------
    // Types
    // -------------------------------------------------------------------------

    struct Session {
        bytes32 sessionId;   // keccak256 hash of the raw session identifier
        bytes32 merkleRoot;  // Merkle root of hashed activity batches
        bytes32 reportHash;  // Canonical report hash (optional for legacy records)
        string modelVersion;
        string featureVersion;
        uint256 heuristicScoreBps;
        string mlClassification;
        uint256 mlConfidenceBps;
        bool synthetic;
        uint256 timestamp;   // block.timestamp at submission time
        address submitter;   // account that called submitSession()
    }

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    address public owner;

    /// @dev sessionId → Session record.  Once written, never mutated.
    mapping(bytes32 => Session) private _sessions;

    /// @dev Tracks which sessionIds have been recorded (for O(1) duplicate check).
    mapping(bytes32 => bool) private _exists;

    /// @dev Accounts permitted to call submitSession().
    mapping(address => bool) private _authorized;

    // -------------------------------------------------------------------------
    // Events
    // -------------------------------------------------------------------------

    /// @notice Emitted each time a new session proof is successfully recorded.
    event SessionRecorded(
        bytes32 indexed sessionId,
        bytes32 merkleRoot,
        address indexed submitter,
        uint256 timestamp
    );

    // -------------------------------------------------------------------------
    // Custom errors  (gas-cheaper than revert strings)
    // -------------------------------------------------------------------------

    error NotOwner();
    error NotAuthorized();
    error ZeroSessionId();
    error ZeroMerkleRoot();
    error DuplicateSession(bytes32 sessionId);
    error SessionNotFound(bytes32 sessionId);

    // -------------------------------------------------------------------------
    // Constructor
    // -------------------------------------------------------------------------

    constructor() {
        owner = msg.sender;
        _authorized[msg.sender] = true; // deployer always authorised
    }

    // -------------------------------------------------------------------------
    // Modifiers
    // -------------------------------------------------------------------------

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAuthorized() {
        if (!_authorized[msg.sender]) revert NotAuthorized();
        _;
    }

    // -------------------------------------------------------------------------
    // Core write function
    // -------------------------------------------------------------------------

    /**
     * @notice Submit a new session proof to the ledger.
     * @param sessionId  keccak256 hash that uniquely identifies the session.
     *                   Must be non-zero and must not have been submitted before.
     * @param merkleRoot Merkle root of the hashed activity-event batches for
     *                   this session. Must be non-zero.
     *
     * Requirements
     * - Caller must be an authorised submitter.
     * - `sessionId` must not be zero.
     * - `merkleRoot` must not be zero.
     * - `sessionId` must not have been previously submitted.
     */
    function submitSession(bytes32 sessionId, bytes32 merkleRoot)
        external
        onlyAuthorized
    {
        _submitSession(sessionId, merkleRoot, bytes32(0), "", "");
    }

    /**
     * @notice Append a session proof with versioned report metadata.
     * Legacy submitSession remains available for existing integrations.
     */
    function submitSessionWithMetadata(
        bytes32 sessionId,
        bytes32 merkleRoot,
        bytes32 reportHash,
        string calldata modelVersion,
        string calldata featureVersion
    ) external onlyAuthorized {
        _submitSession(sessionId, merkleRoot, reportHash, modelVersion, featureVersion);
    }

    function submitSessionWithAnalysis(
        bytes32 sessionId,
        bytes32 merkleRoot,
        bytes32 reportHash,
        string calldata modelVersion,
        string calldata featureVersion,
        uint256 heuristicScoreBps,
        string calldata mlClassification,
        uint256 mlConfidenceBps,
        bool synthetic
    ) external onlyAuthorized {
        _submitSessionWithAnalysis(
            sessionId, merkleRoot, reportHash, modelVersion, featureVersion,
            heuristicScoreBps, mlClassification, mlConfidenceBps, synthetic
        );
    }

    function _submitSession(
        bytes32 sessionId,
        bytes32 merkleRoot,
        bytes32 reportHash,
        string memory modelVersion,
        string memory featureVersion
    ) internal {
        _submitSessionWithAnalysis(
            sessionId, merkleRoot, reportHash, modelVersion, featureVersion,
            0, "", 0, false
        );
    }

    function _submitSessionWithAnalysis(
        bytes32 sessionId,
        bytes32 merkleRoot,
        bytes32 reportHash,
        string memory modelVersion,
        string memory featureVersion,
        uint256 heuristicScoreBps,
        string memory mlClassification,
        uint256 mlConfidenceBps,
        bool synthetic
    ) internal {
        if (sessionId == bytes32(0)) revert ZeroSessionId();
        if (merkleRoot == bytes32(0)) revert ZeroMerkleRoot();
        if (_exists[sessionId]) revert DuplicateSession(sessionId);

        _sessions[sessionId] = Session({
            sessionId: sessionId,
            merkleRoot: merkleRoot,
            reportHash: reportHash,
            modelVersion: modelVersion,
            featureVersion: featureVersion,
            heuristicScoreBps: heuristicScoreBps,
            mlClassification: mlClassification,
            mlConfidenceBps: mlConfidenceBps,
            synthetic: synthetic,
            timestamp: block.timestamp,
            submitter: msg.sender
        });
        _exists[sessionId] = true;

        emit SessionRecorded(sessionId, merkleRoot, msg.sender, block.timestamp);
    }

    // -------------------------------------------------------------------------
    // Read / verification functions
    // -------------------------------------------------------------------------

    /**
     * @notice Retrieve the full Session record for a given sessionId.
     * @param sessionId The session to look up.
     * @return session The stored Session struct.
     * @dev Reverts with `SessionNotFound` if the session has not been submitted.
     */
    function getSession(bytes32 sessionId)
        external
        view
        returns (Session memory session)
    {
        if (!_exists[sessionId]) revert SessionNotFound(sessionId);
        return _sessions[sessionId];
    }

    /**
     * @notice Check whether a given Merkle root matches the one stored for
     *         a session.  Returns false (not revert) when the session does not
     *         exist, so callers can distinguish "wrong root" from "not found".
     * @param sessionId The session to check.
     * @param root      The Merkle root to compare against.
     * @return `true` iff the session exists and its stored merkleRoot equals
     *          `root`.
     */
    function verifyMerkleRoot(bytes32 sessionId, bytes32 root)
        external
        view
        returns (bool)
    {
        if (!_exists[sessionId]) return false;
        return _sessions[sessionId].merkleRoot == root;
    }

    /**
     * @notice Returns whether `sessionId` has already been recorded.
     */
    function sessionExists(bytes32 sessionId) external view returns (bool) {
        return _exists[sessionId];
    }

    // -------------------------------------------------------------------------
    // Access control management
    // -------------------------------------------------------------------------

    /**
     * @notice Grant `account` the right to call submitSession().
     * @dev Only the owner may call this.
     */
    function authorize(address account) external onlyOwner {
        _authorized[account] = true;
    }

    /**
     * @notice Revoke `account`'s right to call submitSession().
     * @dev Only the owner may call this.  Revoking the owner themselves is
     *      possible but inadvisable; the caller is responsible.
     */
    function revoke(address account) external onlyOwner {
        _authorized[account] = false;
    }

    /**
     * @notice Returns whether `account` is currently authorised to submit.
     */
    function isAuthorized(address account) external view returns (bool) {
        return _authorized[account];
    }
}
