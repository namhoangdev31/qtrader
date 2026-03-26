from enum import Enum


class OrderState(Enum):
    NEW = "NEW"
    ACK = "ACK"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"

class OrderFSM:
    """Strict Finite State Machine for order lifecycle management."""
    
    @staticmethod
    def transition(current_state: str, event: str) -> str:
        """
        Transition function: State(t+1) = Transition(State(t), Event)
        
        Transitions according to the FSM:
        NEW -> ACK -> PARTIAL -> FILLED -> CLOSED
                 ↘ REJECTED
        """
        if current_state == OrderState.NEW.value:
            if event == "ACK": return OrderState.ACK.value
            if event == "REJECT": return OrderState.REJECTED.value
            
        if current_state == OrderState.ACK.value:
            if event == "FILL_PARTIAL": return OrderState.PARTIAL.value
            if event == "FILL_COMPLETE": return OrderState.FILLED.value
            if event == "CANCEL": return OrderState.CLOSED.value
            if event == "REJECT": return OrderState.REJECTED.value
            
        if current_state == OrderState.PARTIAL.value:
            if event == "FILL_PARTIAL": return OrderState.PARTIAL.value
            if event == "FILL_COMPLETE": return OrderState.FILLED.value
            if event == "CANCEL": return OrderState.CLOSED.value
            
        # If no transition is defined, return current state or raise (Strict FSM should raise)
        raise ValueError(f"Invalid transition from {current_state} on event {event}")
