from typing import Any

import numpy as np
import polars as pl

from qtrader.core.logger import logger


class FactorRiskEngine:
    """
    Engine for decomposing portfolio risk into defined factors.
    """

    CONFIDENCE_95 = 0.95
    Z_SCORE_95 = 1.645
    Z_SCORE_99 = 2.326

    def decompose_risk(  # noqa: PLR0913
        self,
        positions: dict[str, float],
        prices: dict[str, float],
        factor_exposures: pl.DataFrame,
        factor_covariance: pl.DataFrame,
        idiosyncratic_vols: dict[str, float] | None = None,
        confidence_level: float = 0.95
    ) -> dict[str, Any]:
        """
        Decompose portfolio risk into factors.
        
        Args:
            positions: {symbol: quantity}
            prices: {symbol: current_price}
            factor_exposures: DataFrame with [symbol, factor1, factor2, ...]
            factor_covariance: Covariance matrix of factors (Factor x Factor)
            idiosyncratic_vols: {symbol: annualized_idiosyncratic_vol}
            confidence_level: VaR confidence level
            
        Returns:
            Dictionary with decomposition metrics.
        """
        try:
            # 1. Calculate Weights
            symbols = list(positions.keys())
            values = np.array([positions[s] * prices.get(s, 0.0) for s in symbols])
            total_value = np.sum(np.abs(values))
            
            if total_value == 0:
                return {
                    "total_risk": 0.0,
                    "systematic_risk": 0.0,
                    "specific_risk": 0.0,
                    "factor_exposures": {},
                    "factor_contributions": {},
                    "marginal_vars": {}
                }
                
            # 2. Portfolio Factor Exposure (Beta)
            exp_df = factor_exposures.filter(pl.col("symbol").is_in(symbols))
            if exp_df.is_empty():
                logger.warning("No factor exposures found for portfolio symbols.")
                return {
                    "total_risk": 0.0,
                    "systematic_risk": 0.0,
                    "specific_risk": 0.0,
                    "factor_exposures": {},
                    "factor_contributions": {},
                    "marginal_vars": {}
                }
                
            # Align symbols
            exp_df = exp_df.sort("symbol")
            symbols_sorted = exp_df["symbol"].to_list()
            
            # Use indexed access to align weights with sorted symbols
            weights_raw = np.array([values[symbols.index(s)] for s in symbols_sorted])
            weights_sorted = weights_raw / total_value
            
            # Matrix of betas (Assets x Factors)
            factor_cols = [c for c in exp_df.columns if c != "symbol"]
            x_beta = exp_df.select(factor_cols).to_numpy()
            
            # Portfolio betas (1 x Factors)
            p_beta = weights_sorted @ x_beta
            
            # 3. Factor Risk Contribution
            # Sigma_f (Factors x Factors)
            sigma_f = factor_covariance.select(factor_cols).to_numpy()
            # Factor Variance: p_beta * sigma_f * p_beta'
            systematic_var = p_beta @ sigma_f @ p_beta.T
            
            # 4. Idiosyncratic Risk
            specific_var = 0.0
            if idiosyncratic_vols:
                # sum(w_i^2 * sigma_i^2)
                spec_vols = np.array([idiosyncratic_vols.get(s, 0.0) for s in symbols_sorted])
                specific_var = np.sum((weights_sorted**2) * (spec_vols**2))
                
            total_var = systematic_var + specific_var
            total_vol = np.sqrt(total_var)
            
            # 5. Factor Contributions to Risk (FCTR)
            # FCTR_f = (p_beta,f * (sigma_f * p_beta)_f) / Total_Vol
            if total_vol > 0:
                marginal_contrib_factor = (sigma_f @ p_beta.T) / total_vol
            else:
                marginal_contrib_factor = np.zeros_like(p_beta)
                
            fctr = p_beta * marginal_contrib_factor.flatten()
            
            # 6. Marginal VaR (MVaR)
            # MVaR_f = z_score * Marginal_Contrib_f
            z_score = self.Z_SCORE_95 if confidence_level == self.CONFIDENCE_95 else self.Z_SCORE_99
            mvar = z_score * marginal_contrib_factor.flatten()
            
            return {
                "total_risk": float(total_vol),
                "systematic_risk": float(np.sqrt(systematic_var)),
                "specific_risk": float(np.sqrt(specific_var)),
                "factor_exposures": dict(zip(factor_cols, p_beta.tolist(), strict=True)),
                "factor_contributions": dict(zip(factor_cols, fctr.tolist(), strict=True)),
                "marginal_vars": dict(zip(factor_cols, mvar.tolist(), strict=True)),
                "idiosyncratic_risk_pct": float(specific_var / total_var) if total_var > 0 else 0.0
            }
            
        except Exception as e:
            logger.error(f"Factor risk decomposition failed: {e}")
            return {"error": str(e)}

    def detect_concentration(
        self,
        decomposition: dict[str, Any],
        threshold: float = 0.40
    ) -> list[str]:
        """Detect factors with excessive risk concentration."""
        warnings = []
        total_risk = decomposition.get("total_risk", 0.0)
        if total_risk <= 0:
            return []
            
        contributions = decomposition.get("factor_contributions", {})
        
        for factor, contrib in contributions.items():
            if (contrib / total_risk) > threshold:
                warnings.append(f"High risk concentration in factor: {factor}")
        return warnings
