// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/MockToken.sol";
import "../src/MockProtocol.sol";

contract Deploy is Script {
    function run() external {
        uint256 privateKey  = vm.envUint("PRIVATE_KEY");
        address agentAddress = vm.envAddress("AGENT_ADDRESS");

        vm.startBroadcast(privateKey);

        MockToken mockToken = new MockToken();
        console.log("MockToken deployed at:", address(mockToken));

        MockProtocol mockProtocol = new MockProtocol(address(mockToken), agentAddress);
        console.log("MockProtocol deployed at:", address(mockProtocol));

        // Add initial liquidity
        uint256 liquidityAmount = 5_000 * 10 ** 18;
        mockToken.approve(address(mockProtocol), liquidityAmount);
        mockProtocol.addLiquidity(liquidityAmount);
        console.log("Added 5000 VLT liquidity to MockProtocol");

        vm.stopBroadcast();

        console.log("\n=== DEPLOYMENT COMPLETE ===");
        console.log("MOCK_TOKEN_ADDRESS=", address(mockToken));
        console.log("MOCK_PROTOCOL_ADDRESS=", address(mockProtocol));
    }
}
