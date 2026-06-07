// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/MockToken.sol";
import "../src/MockProtocol.sol";

// Full end-to-end flow test: deposit → attack → agent drains → backup wallet gets funds
contract FullFlowTest is Test {
    MockToken token;
    MockProtocol protocol;

    address owner = address(this);
    address agent = address(0xA6E47);
    address user1 = address(0x1111);
    address user2 = address(0x2222);
    address backup = address(0xBACC);

    uint256 constant ONE_K = 1_000 * 10 ** 18;

    function setUp() public {
        token    = new MockToken();
        protocol = new MockProtocol(address(token), agent);

        token.mint(user1, ONE_K);
        token.mint(user2, ONE_K);
    }

    function testFullDemoFlow() public {
        // Users deposit into MockProtocol
        vm.startPrank(user1);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        vm.startPrank(user2);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        assertEq(protocol.getTVL(), ONE_K * 2);

        // Attack: admin drains 40% of TVL
        uint256 drainAmount = (ONE_K * 2 * 40) / 100;
        protocol.adminTransferFunds(address(0xDEAD), drainAmount);
        uint256 remaining = protocol.getTVL();
        assertEq(remaining, ONE_K * 2 - drainAmount);

        // Agent detects emergency and drains remaining TVL to backup wallet
        vm.prank(agent);
        protocol.agentDrainAll(backup);

        // MockProtocol = 0, backup wallet = remaining funds
        assertEq(protocol.getTVL(), 0);
        assertEq(token.balanceOf(backup), remaining);
    }

    function testOnlyAgentCanDrainAll() public {
        vm.startPrank(user1);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        vm.prank(address(0xBAD));
        vm.expectRevert("Not authorized agent");
        protocol.agentDrainAll(backup);
    }

    function testOnlyOwnerCanAttack() public {
        vm.startPrank(user1);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        vm.prank(address(0xBAD));
        vm.expectRevert("Not owner");
        protocol.adminTransferFunds(address(0xDEAD), ONE_K);
    }
}
