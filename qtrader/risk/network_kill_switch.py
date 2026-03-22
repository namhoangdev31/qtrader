"""Network-level hard kill switch for immediate system termination."""
import socket
import logging
import threading
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)

class KillSwitchState(Enum):
    ARMED = "armed"
    TRIGGERED = "triggered"
    DISABLED = "disabled"

class NetworkKillSwitch:
    """Hard kill switch that terminates network connections at socket level."""
    
    def __init__(self, 
                 trigger_callback: Optional[Callable] = None,
                 restore_callback: Optional[Callable] = None):
        self._state = KillSwitchState.ARMED
        self._trigger_callback = trigger_callback
        self._restore_callback = restore_callback
        self._original_socket_socket = socket.socket
        self._patched = False
        self._lock = threading.RLock()
        
    def arm(self):
        """Arm the kill switch (ready to be triggered)."""
        with self._lock:
            if self._state != KillSwitchState.TRIGGERED:
                self._state = KillSwitchState.ARMED
                logger.info("Network kill switch armed")
                
    def trigger(self):
        """Trigger the kill switch to block all network connections."""
        with self._lock:
            if self._state == KillSwitchState.TRIGGERED:
                return
            self._state = KillSwitchState.TRIGGERED
            logger.critical("NETWORK KILL SWITCH TRIGGERED - Blocking all network connections")
            self._patch_socket()
            if self._trigger_callback:
                try:
                    self._trigger_callback()
                except Exception as e:
                    logger.error(f"Error in kill switch trigger callback: {e}")
                    
    def restore(self):
        """Restore normal network functionality."""
        with self._lock:
            if self._state == KillSwitchState.ARMED:
                return
            self._state = KillSwitchState.ARMED
            logger.info("Restoring network functionality after kill switch")
            self._unpatch_socket()
            if self._restore_callback:
                try:
                    self._restore_callback()
                except Exception as e:
                    logger.error(f"Error in kill switch restore callback: {e}")
                    
    def _patch_socket(self):
        """Patch socket.socket to raise exceptions on all socket operations."""
        if self._patched:
            return
            
        def kill_switch_socket(*args, **kwargs):
            sock = self._original_socket_socket(*args, **kwargs)
            # Replace all socket methods with ones that raise ConnectionError
            original_connect = sock.connect
            original_send = sock.send
            original_recv = sock.recv
            original_sendall = sock.sendall
            
            def blocking_method(*args, **kwargs):
                raise ConnectionError("Network kill switch is active - all network operations blocked")
                
            sock.connect = blocking_method
            sock.send = blocking_method
            sock.recv = blocking_method
            sock.sendall = blocking_method
            sock.shutdown = blocking_method
            sock.close = blocking_method  # Still allow closing to clean up
            return sock
            
        socket.socket = kill_switch_socket
        self._patched = True
        
    def _unpatch_socket(self):
        """Restore original socket.socket."""
        if not self._patched:
            return
        socket.socket = self._original_socket_socket
        self._patched = False
        
    @property
    def is_triggered(self) -> bool:
        """Check if kill switch is currently triggered."""
        return self._state == KillSwitchState.TRIGGERED