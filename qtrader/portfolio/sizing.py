
class KellySizer:
    """Kelly Criterion based position sizing."""
    
    @staticmethod
    def calculate_fraction(win_prob: float, win_loss_ratio: float, fraction: float = 0.5) -> float:
        """
        Calculates the Kelly fraction.
        f* = (p(b+1) - 1) / b
        fraction: usually 0.5 (Half-Kelly) for safety.
        """
        k = (win_prob * (win_loss_ratio + 1) - 1) / win_loss_ratio
        return max(0, k * fraction)

class VolatilitySizer:
    """Volatility-scaled position sizing."""
    
    @staticmethod
    def calculate_quantity(
        capital: float, 
        current_price: float, 
        volatility: float, 
        risk_budget: float = 0.01
    ) -> float:
        """
        Sizes position so that a 1-std move equals the risk budget.
        risk_budget: % of capital to risk per unit of volatility.
        """
        dollar_risk = capital * risk_budget
        # Quantity = Dollar Risk / (Price * Volatility)
        quantity = dollar_risk / (current_price * volatility)
        return quantity
