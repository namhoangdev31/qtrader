import pytest

from qtrader.risk.network_kill_switch import NetworkKillSwitch


def test_kill_switch_initialization():
    switch = NetworkKillSwitch(latency_threshold_ms=500, max_errors=5)
    assert switch.latency_threshold_ms == 500
    assert switch.max_errors == 5
    assert not switch.is_triggered

def test_kill_switch_trigger_on_latency():
    switch = NetworkKillSwitch(latency_threshold_ms=100)
    switch.record_latency(150)
    assert switch.is_triggered

def test_kill_switch_trigger_on_errors():
    switch = NetworkKillSwitch(max_errors=2)
    switch.record_error()
    assert not switch.is_triggered
    switch.record_error()
    assert not switch.is_triggered
    switch.record_error()
    assert switch.is_triggered

def test_kill_switch_reset():
    switch = NetworkKillSwitch(max_errors=1)
    switch.record_error()
    switch.record_error()
    assert switch.is_triggered
    switch.reset()
    assert not switch.is_triggered
