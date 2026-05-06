"""Local ML-based strategy for trading signals"""

import numpy as np
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
import joblib

from src.config import Config
from src.utils.logging import get_logger
from .base import BaseStrategy, Signal, SignalType


logger = get_logger(__name__)


@dataclass
class FeatureVector:
    """Feature vector for ML model"""
    price_change: float
    volume_ratio: float
    liquidity_ratio: float
    bid_ask_spread: float
    momentum: float
    volatility: float
    market_sentiment: float


class MLStrategist(BaseStrategy):
    """
    Machine learning-based trading strategy.

    Uses a Gradient Boosting model trained on historical market features
    to generate trading signals.
    """

    def __init__(self, config: Config):
        super().__init__(config)

        # Model configuration
        self.model_path = config.get("ml_model_path", "models/ml_model.pkl")
        self.scaler_path = config.get("scaler_path", "models/scaler.pkl")

        # Load model if exists, otherwise create new
        self.model = self._load_or_create_model()
        self.scaler = self._load_or_create_scaler()

        # Feature parameters
        self.lookback_periods = [5, 15, 30]  # minutes
        self.threshold = 0.6  # Confidence threshold

    def _load_or_create_model(self) -> GradientBoostingClassifier:
        """Load existing model or create new one"""
        try:
            return joblib.load(self.model_path)
        except FileNotFoundError:
            logger.info("No existing model found, creating new one")
            return GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )

    def _load_or_create_scaler(self) -> StandardScaler:
        """Load existing scaler or create new one"""
        try:
            return joblib.load(self.scaler_path)
        except FileNotFoundError:
            logger.info("No existing scaler found, creating new one")
            return StandardScaler()

    async def analyze(self, market: Dict[str, Any]) -> Optional[Signal]:
        """Analyze market and generate signal using ML model"""
        try:
            # Extract features
            features = self._extract_features(market)

            if features is None:
                return None

            # Scale features
            features_scaled = self.scaler.transform([features])

            # Get prediction
            prediction = self.model.predict(features_scaled)[0]
            probabilities = self.model.predict_proba(features_scaled)[0]

            confidence = max(probabilities)

            if confidence < self.threshold:
                return None

            # Determine signal type
            signal_type = SignalType.BUY if prediction == 1 else SignalType.SELL

            # Get token ID for the predicted outcome
            token_id = self._get_token_id_for_prediction(market, prediction)

            return Signal(
                signal_type=signal_type,
                market_id=market.get("id", ""),
                token_id=token_id,
                confidence=confidence,
                price=features[0],  # Current price as target
                reason=f"ML prediction with {confidence:.1%} confidence",
                metadata={"probabilities": probabilities.tolist()}
            )

        except Exception as e:
            logger.error(f"ML analysis failed: {e}")
            return None

    async def on_tick(self, markets: List[Dict[str, Any]]) -> List[Signal]:
        """Analyze multiple markets"""
        signals = []
        for market in markets:
            signal = await self.analyze(market)
            if signal:
                signals.append(signal)
        return signals

    async def learn(self, historical_data: List[Dict]) -> None:
        """
        Train the model on historical data.

        historical_data should contain:
        - features: list of FeatureVector
        - labels: list of 0/1 (should buy or not)
        """
        try:
            X = np.array([self._features_to_array(f) for f in historical_data])
            y = np.array([d["label"] for d in historical_data])

            # Fit scaler
            X_scaled = self.scaler.fit_transform(X)

            # Train model
            self.model.fit(X_scaled, y)

            # Save model and scaler
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)

            logger.info(f"Model trained on {len(y)} samples")

        except Exception as e:
            logger.error(f"Training failed: {e}")

    def _extract_features(self, market: Dict[str, Any]) -> Optional[list]:
        """Extract features from market data for ML model"""
        try:
            # Price change
            current_price = float(market.get('outcomePrices', [0.5])[1] or 0.5)
            previous_price = market.get('previous_price', current_price)
            price_change = current_price - previous_price

            # Volume features
            volume = float(market.get('volume', 0))
            avg_volume = market.get('avg_volume', volume)
            volume_ratio = volume / max(avg_volume, 1)

            # Liquidity features
            liquidity = float(market.get('liquidity', 0))
            volume_for_liquidity = volume
            liquidity_ratio = volume_for_liquidity / max(liquidity, 1)

            # Bid-ask spread
            outcomes = market.get('outcomePrices', [0.5, 0.5])
            if len(outcomes) >= 2:
                bid_ask_spread = abs(float(outcomes[0]) - float(outcomes[1]))
            else:
                bid_ask_spread = 0.1

            # Momentum (simplified)
            momentum = price_change * 10

            # Volatility (simplified using price range)
            high = market.get('high_price', current_price)
            low = market.get('low_price', current_price)
            volatility = (high - low) / max(current_price, 0.01)

            # Market sentiment (based on volume trend)
            market_sentiment = min(volume_ratio / 2, 1.0)

            return [
                price_change,
                volume_ratio,
                liquidity_ratio,
                bid_ask_spread,
                momentum,
                volatility,
                market_sentiment
            ]

        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            return None

    def _features_to_array(self, features) -> list:
        """Convert features to numpy array"""
        if isinstance(features, FeatureVector):
            return [
                features.price_change,
                features.volume_ratio,
                features.liquidity_ratio,
                features.bid_ask_spread,
                features.momentum,
                features.volatility,
                features.market_sentiment
            ]
        return features

    def _get_token_id_for_prediction(self, market: Dict, prediction: int) -> str:
        """Get token ID based on ML prediction"""
        try:
            token_ids = market.get('clob_token_ids', [])
            if isinstance(token_ids, str):
                import ast
                token_ids = ast.literal_eval(token_ids)

            # Prediction 1 = YES (buy), 0 = NO (sell)
            # In Polymarket, token index 1 is typically YES
            return token_ids[prediction] if prediction < len(token_ids) else token_ids[0]

        except Exception:
            return ""

    def save_model(self) -> None:
        """Save trained model to disk"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            logger.info("Model saved successfully")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")

    def load_model(self) -> bool:
        """Load model from disk"""
        try:
            self.model = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)
            logger.info("Model loaded successfully")
            return True
        except FileNotFoundError:
            logger.warning("No model found to load")
            return False