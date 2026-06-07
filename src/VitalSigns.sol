// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VitalSigns {
    address public owner;
    address public authorizedAgent;

    struct UserRegistration {
        address userAddress;
        address safeWallet;
        bool isRegistered;
    }

    struct HealthReport {
        string tvlStatus;
        string adminStatus;
        string liquidityStatus;
        string txPatternStatus;
        string upgradeStatus;
        string overallRisk;
        string aiDiagnosis;
        uint256 timestamp;
    }

    mapping(address => UserRegistration) public registeredUsers;
    address[] public userList;
    HealthReport[] public reportHistory;
    HealthReport public latestReport;
    bool public emergencyActive;

    event UserRegistered(address user, address safeWallet);
    event HealthReportPublished(string overallRisk, string aiDiagnosis, uint256 timestamp);
    event EmergencyActivated(string diagnosis, uint256 timestamp);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyAgent() {
        require(msg.sender == authorizedAgent, "Not authorized agent");
        _;
    }

    constructor(address agentAddress) {
        owner = msg.sender;
        authorizedAgent = agentAddress;
    }

    // Register your safe wallet — no token deposit needed
    function registerForProtection(address safeWallet) external {
        require(!registeredUsers[msg.sender].isRegistered, "Already registered");
        require(safeWallet != address(0), "Invalid safe wallet");

        registeredUsers[msg.sender] = UserRegistration({
            userAddress: msg.sender,
            safeWallet: safeWallet,
            isRegistered: true
        });

        userList.push(msg.sender);
        emit UserRegistered(msg.sender, safeWallet);
    }

    function publishHealthReport(
        string calldata tvlStatus,
        string calldata adminStatus,
        string calldata liquidityStatus,
        string calldata txPatternStatus,
        string calldata upgradeStatus,
        string calldata overallRisk,
        string calldata aiDiagnosis
    ) external onlyAgent {
        HealthReport memory report = HealthReport({
            tvlStatus: tvlStatus,
            adminStatus: adminStatus,
            liquidityStatus: liquidityStatus,
            txPatternStatus: txPatternStatus,
            upgradeStatus: upgradeStatus,
            overallRisk: overallRisk,
            aiDiagnosis: aiDiagnosis,
            timestamp: block.timestamp
        });

        reportHistory.push(report);
        latestReport = report;

        emit HealthReportPublished(overallRisk, aiDiagnosis, block.timestamp);

        if (keccak256(bytes(overallRisk)) == keccak256(bytes("EMERGENCY"))) {
            emergencyActive = true;
            emit EmergencyActivated(aiDiagnosis, block.timestamp);
        }
    }

    function getLatestReport() external view returns (HealthReport memory) {
        return latestReport;
    }

    function getReportHistory() external view returns (HealthReport[] memory) {
        return reportHistory;
    }

    function getRegisteredUsers() external view returns (address[] memory) {
        return userList;
    }

    function getUserRegistration(address user) external view returns (UserRegistration memory) {
        return registeredUsers[user];
    }

    function setAuthorizedAgent(address newAgent) external onlyOwner {
        authorizedAgent = newAgent;
    }

    function resetDemo() external onlyOwner {
        emergencyActive = false;
    }
}
