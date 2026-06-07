// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/MockToken.sol";
import "../src/MockProtocol.sol";

contract MockProtocolTest is Test {
    MockToken token;
    MockProtocol protocol;

    address owner = address(this);
    address agent = address(0xA6E47);
    address user = address(0xBEEF);
    address safe = address(0x5AFE);
    address randomAddr = address(0xDEAD);

    uint256 constant ONE_K = 1_000 * 10 ** 18;
    uint256 constant FIVE_HUNDRED = 500 * 10 ** 18;

    function setUp() public {
        token = new MockToken();
        protocol = new MockProtocol(address(token), agent);

        // Fund user with tokens
        token.mint(user, 10_000 * 10 ** 18);
    }

    function testDeposit() public {
        vm.startPrank(user);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        assertEq(protocol.getTVL(), ONE_K);
        assertEq(protocol.userDeposits(user), ONE_K);
    }

    function testWithdraw() public {
        vm.startPrank(user);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);

        uint256 balanceBefore = token.balanceOf(user);
        protocol.withdraw(FIVE_HUNDRED);
        vm.stopPrank();

        assertEq(protocol.getTVL(), FIVE_HUNDRED);
        assertEq(protocol.userDeposits(user), FIVE_HUNDRED);
        assertEq(token.balanceOf(user), balanceBefore + FIVE_HUNDRED);
    }

    function testAdminDrainSimulation() public {
        vm.startPrank(user);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        assertEq(protocol.getTVL(), ONE_K);

        uint256 drainAmount = 800 * 10 ** 18;
        protocol.adminTransferFunds(randomAddr, drainAmount);

        assertEq(protocol.getTVL(), ONE_K - drainAmount);
        assertEq(token.balanceOf(randomAddr), drainAmount);
    }

    function testAgentDrainAll() public {
        // User deposits 1000 VLT into MockProtocol
        vm.startPrank(user);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        vm.stopPrank();

        assertEq(protocol.getTVL(), ONE_K);

        // Agent drains all remaining TVL to safe wallet
        vm.prank(agent);
        protocol.agentDrainAll(safe);

        // MockProtocol TVL should be 0, safe wallet has 1000 VLT
        assertEq(protocol.getTVL(), 0);
        assertEq(token.balanceOf(safe), ONE_K);
    }

    function testLiquidityRemoval() public {
        uint256 addAmount = 500 * 10 ** 18;
        uint256 removeAmount = 300 * 10 ** 18;

        token.approve(address(protocol), addAmount);
        protocol.addLiquidity(addAmount);
        assertEq(protocol.getLiquidity(), addAmount);

        protocol.removeLiquidity(removeAmount);
        assertEq(protocol.getLiquidity(), addAmount - removeAmount);
    }

    function testTransactionCountIncrement() public {
        vm.startPrank(user);
        token.approve(address(protocol), ONE_K);
        protocol.deposit(ONE_K);
        protocol.withdraw(FIVE_HUNDRED);
        vm.stopPrank();

        assertEq(protocol.getTransactionCount(), 2);
    }
}
