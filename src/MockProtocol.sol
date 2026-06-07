// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract MockProtocol {
    address public owner;
    address public authorizedAgent;
    IERC20 public token;
    uint256 public totalDeposits;
    uint256 public liquidityBalance;
    uint256 public transactionCount;
    mapping(address => uint256) public userDeposits;

    event Deposited(address user, uint256 amount);
    event Withdrawn(address user, uint256 amount);
    event LiquidityAdded(uint256 amount);
    event LiquidityRemoved(uint256 amount);
    event AdminTransfer(address to, uint256 amount);
    event EmergencyDrain(address to, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyAgent() {
        require(msg.sender == authorizedAgent, "Not authorized agent");
        _;
    }

    constructor(address tokenAddress, address agentAddress) {
        owner = msg.sender;
        authorizedAgent = agentAddress;
        token = IERC20(tokenAddress);
    }

    function setAuthorizedAgent(address agent) external onlyOwner {
        authorizedAgent = agent;
    }

    function deposit(uint256 amount) external {
        require(amount > 0, "Amount must be > 0");
        token.transferFrom(msg.sender, address(this), amount);
        userDeposits[msg.sender] += amount;
        totalDeposits += amount;
        transactionCount++;
        emit Deposited(msg.sender, amount);
    }

    function withdraw(uint256 amount) external {
        require(userDeposits[msg.sender] >= amount, "Insufficient balance");
        userDeposits[msg.sender] -= amount;
        totalDeposits -= amount;
        transactionCount++;
        token.transfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    // Agent calls this on EMERGENCY — drains ALL remaining TVL to the safe backup wallet
    function agentDrainAll(address to) external onlyAgent {
        uint256 amount = totalDeposits;
        require(amount > 0, "Nothing to drain");
        totalDeposits = 0;
        token.transfer(to, amount);
        emit EmergencyDrain(to, amount);
    }

    function addLiquidity(uint256 amount) external onlyOwner {
        token.transferFrom(msg.sender, address(this), amount);
        liquidityBalance += amount;
        emit LiquidityAdded(amount);
    }

    function removeLiquidity(uint256 amount) external onlyOwner {
        require(liquidityBalance >= amount, "Insufficient liquidity");
        liquidityBalance -= amount;
        token.transfer(msg.sender, amount);
        emit LiquidityRemoved(amount);
    }

    // Admin drains TVL — simulates rug pull attack
    function adminTransferFunds(address to, uint256 amount) external onlyOwner {
        require(totalDeposits >= amount, "Insufficient deposits");
        totalDeposits -= amount;
        token.transfer(to, amount);
        emit AdminTransfer(to, amount);
    }

    function getTVL() external view returns (uint256) {
        return totalDeposits;
    }

    function getLiquidity() external view returns (uint256) {
        return liquidityBalance;
    }

    function getTransactionCount() external view returns (uint256) {
        return transactionCount;
    }
}
