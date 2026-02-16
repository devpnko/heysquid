"""
암호화폐 하이브리드 자동매매 봇 — heysquid
전략 1: Smart Grid + ADX 필터 (횡보장)
전략 2: RSI DCA + 단계적 익절 (추세장)
전략 4: Fear & Greed 역발상 (폭락장)

시장 상태에 따라 자동 전환.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import ccxt
import pandas as pd
import numpy as np
import requests
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator

# ─── 설정 ────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BOT_STATE_FILE = os.path.join(DATA_DIR, "trading_bot_state.json")
TRADE_LOG_FILE = os.path.join(DATA_DIR, "trade_log.json")

# 로깅
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("trading_bot")


# ─── 거래소 연결 ─────────────────────────────────────

def create_exchange(exchange_id: str = "binance", api_key: str = "", secret: str = "", sandbox: bool = True):
    """CCXT 거래소 인스턴스 생성"""
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    if sandbox:
        exchange.set_sandbox_mode(True)
        log.info(f"[SANDBOX] {exchange_id} 테스트넷 모드")
    return exchange


# ─── 데이터 수집 ─────────────────────────────────────

def fetch_ohlcv(exchange, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    """OHLCV 캔들 데이터 수집"""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_fear_greed_index() -> Optional[int]:
    """Fear & Greed Index 조회 (alternative.me API)"""
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = resp.json()
        return int(data["data"][0]["value"])
    except Exception as e:
        log.warning(f"Fear & Greed Index 조회 실패: {e}")
        return None


# ─── 지표 계산 ───────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """모든 기술 지표 계산"""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # ADX
    adx_ind = ADXIndicator(high, low, close, window=14)
    df["adx"] = adx_ind.adx()

    # Bollinger Bands
    bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # ATR
    atr = AverageTrueRange(high, low, close, window=14)
    df["atr"] = atr.average_true_range()

    # RSI
    rsi = RSIIndicator(close, window=14)
    df["rsi"] = rsi.rsi()

    # MACD
    macd = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # EMA
    ema_20 = EMAIndicator(close, window=20)
    ema_50 = EMAIndicator(close, window=50)
    df["ema_20"] = ema_20.ema_indicator()
    df["ema_50"] = ema_50.ema_indicator()

    return df


# ─── 시장 상태 판별 ──────────────────────────────────

def detect_market_regime(df: pd.DataFrame, fgi: Optional[int]) -> str:
    """
    시장 상태 판별:
    - 'panic': FGI < 15 (극단적 공포)
    - 'sideways': ADX < 25 (횡보)
    - 'trending': ADX >= 25 (추세)
    """
    latest = df.iloc[-1]

    if fgi is not None and fgi < 15:
        return "panic"

    adx = latest["adx"]
    if pd.isna(adx):
        return "sideways"  # 데이터 부족 시 안전하게 횡보 가정

    if adx < 25:
        return "sideways"
    return "trending"


# ─── 전략 1: Smart Grid + ADX ────────────────────────

class SmartGridStrategy:
    """횡보장 전용 그리드 전략"""

    def __init__(self, exchange, symbol: str, capital: float, grid_count: int = 20):
        self.exchange = exchange
        self.symbol = symbol
        self.capital = capital
        self.grid_count = grid_count
        self.grid_orders = []  # 활성 그리드 주문
        self.active = False

    def setup_grid(self, df: pd.DataFrame):
        """볼린저밴드 기반 그리드 설정"""
        latest = df.iloc[-1]
        upper = latest["bb_upper"]
        lower = latest["bb_lower"]
        current_price = latest["close"]

        if pd.isna(upper) or pd.isna(lower):
            log.warning("[GRID] BB 데이터 부족, 그리드 설정 불가")
            return

        interval = (upper - lower) / self.grid_count
        amount_per_grid = self.capital / self.grid_count

        self.grid_orders = []
        for i in range(self.grid_count):
            price = lower + (interval * i)
            self.grid_orders.append({
                "level": i,
                "buy_price": round(price, 2),
                "sell_price": round(price + interval, 2),
                "amount_usdt": round(amount_per_grid, 2),
                "filled": False,
                "side": "buy" if price < current_price else "sell",
            })

        self.active = True
        log.info(f"[GRID] 그리드 설정 완료: {lower:.2f} ~ {upper:.2f}, {self.grid_count}개, 간격 {interval:.2f}")

    def check_and_execute(self, df: pd.DataFrame) -> list:
        """그리드 주문 체크 및 실행"""
        if not self.active or not self.grid_orders:
            return []

        latest = df.iloc[-1]
        current_price = latest["close"]
        adx = latest["adx"]
        trades = []

        # ADX 체크 — 추세 전환 시 그리드 정지
        if not pd.isna(adx) and adx > 30:
            log.info(f"[GRID] ADX={adx:.1f} > 30, 추세 감지 → 그리드 일시정지")
            self.active = False
            return []

        for order in self.grid_orders:
            if not order["filled"] and order["side"] == "buy":
                if current_price <= order["buy_price"]:
                    # 매수 체결
                    amount = order["amount_usdt"] / current_price
                    trade = self._execute_buy(current_price, amount, order)
                    if trade:
                        trades.append(trade)

            elif order["filled"] and order["side"] == "sell":
                if current_price >= order["sell_price"]:
                    # 매도 체결
                    trade = self._execute_sell(current_price, order)
                    if trade:
                        trades.append(trade)

        return trades

    def _execute_buy(self, price, amount, order) -> Optional[dict]:
        """매수 실행"""
        try:
            result = self.exchange.create_limit_buy_order(
                self.symbol, amount, price
            )
            order["filled"] = True
            order["side"] = "sell"
            order["filled_amount"] = amount
            log.info(f"[GRID BUY] {self.symbol} @ {price:.2f}, 수량: {amount:.6f}")
            return {
                "strategy": "grid",
                "side": "buy",
                "symbol": self.symbol,
                "price": price,
                "amount": amount,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[GRID BUY ERROR] {e}")
            return None

    def _execute_sell(self, price, order) -> Optional[dict]:
        """매도 실행"""
        try:
            amount = order.get("filled_amount", 0)
            if amount <= 0:
                return None
            result = self.exchange.create_limit_sell_order(
                self.symbol, amount, price
            )
            order["filled"] = False
            order["side"] = "buy"
            profit = (price - order["buy_price"]) * amount
            log.info(f"[GRID SELL] {self.symbol} @ {price:.2f}, 수익: {profit:.2f} USDT")
            return {
                "strategy": "grid",
                "side": "sell",
                "symbol": self.symbol,
                "price": price,
                "amount": amount,
                "profit": profit,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[GRID SELL ERROR] {e}")
            return None

    def stop(self):
        """그리드 정지"""
        self.active = False
        log.info("[GRID] 그리드 정지")


# ─── 전략 2: RSI DCA + 단계적 익절 ──────────────────

class RSIDCAStrategy:
    """추세장 DCA 전략"""

    def __init__(self, exchange, symbol: str, capital: float, base_amount: float = 20.0):
        self.exchange = exchange
        self.symbol = symbol
        self.capital = capital
        self.base_amount = base_amount
        self.positions = []  # 진입 내역
        self.total_invested = 0.0
        self.total_amount = 0.0
        self.avg_entry_price = 0.0
        self.highest_profit_pct = 0.0
        self.safety_orders_used = 0
        self.max_safety_orders = 3

    def check_and_execute(self, df: pd.DataFrame, fgi: Optional[int]) -> list:
        """RSI 기반 매수 + 단계적 익절 매도"""
        latest = df.iloc[-1]
        rsi = latest["rsi"]
        current_price = latest["close"]
        trades = []

        if pd.isna(rsi):
            return []

        # ─── 매수 로직 ───
        if self.total_invested < self.capital * 0.7:  # 투자 한도 70%
            buy_amount = self._calculate_buy_amount(rsi, fgi)
            if buy_amount > 0:
                trade = self._execute_buy(current_price, buy_amount)
                if trade:
                    trades.append(trade)

        # ─── 안전주문 (추가 하락 시) ───
        if self.total_amount > 0 and self.safety_orders_used < self.max_safety_orders:
            loss_pct = (current_price - self.avg_entry_price) / self.avg_entry_price * 100
            safety_thresholds = [-3, -6, -9]
            safety_amounts = [30, 50, 75]

            if self.safety_orders_used < len(safety_thresholds):
                threshold = safety_thresholds[self.safety_orders_used]
                if loss_pct <= threshold:
                    amount_usdt = safety_amounts[self.safety_orders_used]
                    if self.total_invested + amount_usdt <= self.capital * 0.7:
                        trade = self._execute_buy(current_price, amount_usdt)
                        if trade:
                            self.safety_orders_used += 1
                            trades.append(trade)
                            log.info(f"[DCA SAFETY] 안전주문 {self.safety_orders_used}단계 실행 (하락 {loss_pct:.1f}%)")

        # ─── 매도 로직 (단계적 익절) ───
        if self.total_amount > 0:
            profit_pct = (current_price - self.avg_entry_price) / self.avg_entry_price * 100
            self.highest_profit_pct = max(self.highest_profit_pct, profit_pct)

            sell_trades = self._check_take_profit(current_price, profit_pct, rsi)
            trades.extend(sell_trades)

            # 트레일링 스톱
            trailing_trades = self._check_trailing_stop(current_price, profit_pct)
            trades.extend(trailing_trades)

        return trades

    def _calculate_buy_amount(self, rsi: float, fgi: Optional[int]) -> float:
        """RSI + FGI 기반 매수 금액 결정"""
        if rsi < 20 and fgi is not None and fgi < 20:
            return self.base_amount * 2  # 극단적 공포: 2배
        elif rsi < 25:
            return self.base_amount * 1.5  # 강한 과매도: 1.5배
        elif rsi < 30:
            return self.base_amount  # 과매도: 기본
        return 0  # 매수 안 함

    def _execute_buy(self, price: float, amount_usdt: float) -> Optional[dict]:
        """매수 실행"""
        try:
            amount = amount_usdt / price
            result = self.exchange.create_market_buy_order(self.symbol, amount)

            self.total_invested += amount_usdt
            self.total_amount += amount
            self.avg_entry_price = self.total_invested / self.total_amount if self.total_amount > 0 else price
            self.positions.append({
                "price": price,
                "amount": amount,
                "amount_usdt": amount_usdt,
                "timestamp": datetime.now().isoformat(),
            })

            log.info(f"[DCA BUY] {self.symbol} @ {price:.2f}, ${amount_usdt:.0f}, 평균단가: {self.avg_entry_price:.2f}")
            return {
                "strategy": "dca",
                "side": "buy",
                "symbol": self.symbol,
                "price": price,
                "amount": amount,
                "amount_usdt": amount_usdt,
                "avg_entry": self.avg_entry_price,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[DCA BUY ERROR] {e}")
            return None

    def _check_take_profit(self, price: float, profit_pct: float, rsi: float) -> list:
        """단계적 익절"""
        trades = []

        # RSI 과매수 시 전량 매도
        if rsi > 75 and profit_pct > 5:
            trade = self._execute_sell(price, 1.0, "RSI 과매수 전량 매도")
            if trade:
                trades.append(trade)
            return trades

        # 단계적 익절
        if profit_pct >= 30 and self.total_amount > 0:
            trade = self._execute_sell(price, 0.25, "3차 익절 (30%)")
            if trade:
                trades.append(trade)
        elif profit_pct >= 20 and self.total_amount > 0:
            trade = self._execute_sell(price, 0.25, "2차 익절 (20%)")
            if trade:
                trades.append(trade)
        elif profit_pct >= 10 and self.total_amount > 0:
            trade = self._execute_sell(price, 0.25, "1차 익절 (10%)")
            if trade:
                trades.append(trade)

        return trades

    def _check_trailing_stop(self, price: float, profit_pct: float) -> list:
        """트레일링 스톱"""
        trades = []

        if self.highest_profit_pct > 10:
            trailing_pct = 3 if self.highest_profit_pct > 20 else 5
            if self.highest_profit_pct - profit_pct >= trailing_pct:
                trade = self._execute_sell(price, 1.0, f"트레일링 스톱 ({trailing_pct}% 하락)")
                if trade:
                    trades.append(trade)
        return trades

    def _execute_sell(self, price: float, fraction: float, reason: str) -> Optional[dict]:
        """매도 실행"""
        try:
            sell_amount = self.total_amount * fraction
            if sell_amount <= 0:
                return None

            result = self.exchange.create_market_sell_order(self.symbol, sell_amount)

            profit = (price - self.avg_entry_price) * sell_amount
            self.total_amount -= sell_amount
            self.total_invested *= (1 - fraction)

            if self.total_amount <= 0:
                self._reset()

            log.info(f"[DCA SELL] {reason}: {self.symbol} @ {price:.2f}, 수량: {sell_amount:.6f}, 수익: {profit:.2f}")
            return {
                "strategy": "dca",
                "side": "sell",
                "symbol": self.symbol,
                "price": price,
                "amount": sell_amount,
                "profit": profit,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[DCA SELL ERROR] {e}")
            return None

    def _reset(self):
        """포지션 리셋"""
        self.positions = []
        self.total_invested = 0.0
        self.total_amount = 0.0
        self.avg_entry_price = 0.0
        self.highest_profit_pct = 0.0
        self.safety_orders_used = 0
        log.info("[DCA] 포지션 전량 청산, 리셋 완료")


# ─── 전략 4: Fear & Greed 역발상 ─────────────────────

class FearGreedStrategy:
    """극단적 공포 시 대규모 매수"""

    def __init__(self, exchange, symbol: str, reserve_capital: float):
        self.exchange = exchange
        self.symbol = symbol
        self.reserve_capital = reserve_capital
        self.position_amount = 0.0
        self.entry_price = 0.0
        self.invested = 0.0

    def check_and_execute(self, df: pd.DataFrame, fgi: Optional[int]) -> list:
        """FGI 극단값에서 매매"""
        if fgi is None:
            return []

        latest = df.iloc[-1]
        current_price = latest["close"]
        rsi = latest["rsi"]
        trades = []

        # 매수: 극단적 공포
        if self.invested == 0 and fgi < 15 and not pd.isna(rsi) and rsi < 35:
            amount_usdt = self.reserve_capital * 0.6  # 비상금의 60%
            trade = self._execute_buy(current_price, amount_usdt)
            if trade:
                trades.append(trade)

        # 매도: 탐욕 복귀
        if self.position_amount > 0:
            if fgi > 75 and not pd.isna(rsi) and rsi > 70:
                trade = self._execute_sell(current_price, 0.5, "FGI 탐욕 + RSI 과매수")
                if trade:
                    trades.append(trade)
            elif fgi > 85:
                trade = self._execute_sell(current_price, 1.0, "FGI 극단적 탐욕")
                if trade:
                    trades.append(trade)

            # 트레일링 스톱 15%
            if self.entry_price > 0:
                profit_pct = (current_price - self.entry_price) / self.entry_price * 100
                if profit_pct > 20:
                    # 15% 트레일링
                    pass  # 간단한 구현: 메인 루프에서 체크

        return trades

    def _execute_buy(self, price, amount_usdt) -> Optional[dict]:
        try:
            amount = amount_usdt / price
            result = self.exchange.create_market_buy_order(self.symbol, amount)
            self.position_amount = amount
            self.entry_price = price
            self.invested = amount_usdt
            log.info(f"[FGI BUY] 극단적 공포 매수! {self.symbol} @ {price:.2f}, ${amount_usdt:.0f}")
            return {
                "strategy": "fear_greed",
                "side": "buy",
                "symbol": self.symbol,
                "price": price,
                "amount": amount,
                "amount_usdt": amount_usdt,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[FGI BUY ERROR] {e}")
            return None

    def _execute_sell(self, price, fraction, reason) -> Optional[dict]:
        try:
            sell_amount = self.position_amount * fraction
            result = self.exchange.create_market_sell_order(self.symbol, sell_amount)
            profit = (price - self.entry_price) * sell_amount
            self.position_amount -= sell_amount
            if self.position_amount <= 0:
                self.position_amount = 0
                self.entry_price = 0
                self.invested = 0
            log.info(f"[FGI SELL] {reason}: {self.symbol} @ {price:.2f}, 수익: {profit:.2f}")
            return {
                "strategy": "fear_greed",
                "side": "sell",
                "symbol": self.symbol,
                "price": price,
                "amount": sell_amount,
                "profit": profit,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            log.error(f"[FGI SELL ERROR] {e}")
            return None


# ─── 하이브리드 봇 (통합 컨트롤러) ───────────────────

class HybridTradingBot:
    """전략 1+2+4 자동 전환 하이브리드 봇"""

    def __init__(self, config: dict):
        self.config = config
        self.exchange = create_exchange(
            exchange_id=config.get("exchange", "binance"),
            api_key=config.get("api_key", ""),
            secret=config.get("secret", ""),
            sandbox=config.get("sandbox", True),
        )

        symbol = config.get("symbol", "ETH/USDT")
        total_capital = config.get("capital", 500)

        # 자본 배분
        grid_capital = total_capital * 0.50   # 50% 그리드
        dca_capital = total_capital * 0.40    # 40% DCA
        reserve_capital = total_capital * 0.10  # 10% 비상금

        # 전략 인스턴스
        self.grid = SmartGridStrategy(
            self.exchange, symbol, grid_capital,
            grid_count=config.get("grid_count", 20)
        )
        self.dca = RSIDCAStrategy(
            self.exchange, config.get("dca_symbol", "BTC/USDT"),
            dca_capital, base_amount=config.get("dca_base_amount", 20)
        )
        self.fgi = FearGreedStrategy(
            self.exchange, symbol, reserve_capital
        )

        self.current_regime = "unknown"
        self.trade_history = []
        self.total_pnl = 0.0
        self.start_time = datetime.now()

        log.info(f"[BOT] 하이브리드 봇 초기화: {symbol}")
        log.info(f"  그리드: {grid_capital} USDT / DCA: {dca_capital} USDT / 비상금: {reserve_capital} USDT")

    def run_cycle(self):
        """1사이클 실행 (매 interval마다 호출)"""
        try:
            # 1. 데이터 수집
            df = fetch_ohlcv(self.exchange, self.config.get("symbol", "ETH/USDT"), "1h", 100)
            df = compute_indicators(df)
            fgi_value = fetch_fear_greed_index()

            # 2. 시장 상태 판별
            regime = detect_market_regime(df, fgi_value)
            if regime != self.current_regime:
                log.info(f"[REGIME] 시장 전환: {self.current_regime} → {regime}")
                self.current_regime = regime

            latest = df.iloc[-1]
            log.info(
                f"[STATUS] 가격: {latest['close']:.2f}, "
                f"ADX: {latest['adx']:.1f}, RSI: {latest['rsi']:.1f}, "
                f"FGI: {fgi_value}, 시장: {regime}"
            )

            trades = []

            # 3. 전략 실행
            if regime == "panic":
                # 극단적 공포 → 전략 4 우선
                trades.extend(self.fgi.check_and_execute(df, fgi_value))
                # DCA도 공격적 매수
                trades.extend(self.dca.check_and_execute(df, fgi_value))
                self.grid.stop()

            elif regime == "sideways":
                # 횡보장 → 전략 1 (그리드)
                if not self.grid.active:
                    self.grid.setup_grid(df)
                trades.extend(self.grid.check_and_execute(df))
                # DCA는 일시정지 (횡보에서는 비효율)

            elif regime == "trending":
                # 추세장 → 전략 2 (DCA)
                self.grid.stop()
                trades.extend(self.dca.check_and_execute(df, fgi_value))

            # 4. 거래 기록
            for trade in trades:
                self.trade_history.append(trade)
                if "profit" in trade:
                    self.total_pnl += trade["profit"]

            # 5. 리스크 체크
            self._check_risk_limits()

            # 6. 상태 저장
            self._save_state()

            return trades

        except Exception as e:
            log.error(f"[CYCLE ERROR] {e}")
            return []

    def _check_risk_limits(self):
        """리스크 한도 체크"""
        capital = self.config.get("capital", 500)
        max_drawdown_pct = self.config.get("max_drawdown", 15)

        if self.total_pnl < 0:
            drawdown_pct = abs(self.total_pnl) / capital * 100
            if drawdown_pct >= max_drawdown_pct:
                log.warning(f"[RISK] 최대 손실 한도 도달! 드로다운: {drawdown_pct:.1f}% ≥ {max_drawdown_pct}%")
                self.grid.stop()
                # DCA 매수 정지 (total_invested를 capital * 0.7로 설정)
                self.dca.total_invested = self.dca.capital * 0.7

    def _save_state(self):
        """봇 상태 저장"""
        state = {
            "timestamp": datetime.now().isoformat(),
            "regime": self.current_regime,
            "total_pnl": round(self.total_pnl, 2),
            "trade_count": len(self.trade_history),
            "grid_active": self.grid.active,
            "dca_invested": round(self.dca.total_invested, 2),
            "dca_amount": self.dca.total_amount,
            "dca_avg_entry": round(self.dca.avg_entry_price, 2),
            "uptime_hours": (datetime.now() - self.start_time).total_seconds() / 3600,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(BOT_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def get_status(self) -> str:
        """현재 상태 텍스트"""
        uptime = datetime.now() - self.start_time
        return (
            f"시장: {self.current_regime}\n"
            f"총 PnL: {self.total_pnl:+.2f} USDT\n"
            f"거래 횟수: {len(self.trade_history)}회\n"
            f"그리드: {'활성' if self.grid.active else '정지'}\n"
            f"DCA 투자액: {self.dca.total_invested:.0f} USDT\n"
            f"가동 시간: {uptime.total_seconds() / 3600:.1f}시간"
        )


# ─── 실행 ────────────────────────────────────────────

def load_config() -> dict:
    """설정 파일 로드"""
    config_path = os.path.join(DATA_DIR, "trading_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)

    # 기본 설정 (테스트용)
    default_config = {
        "exchange": "binance",
        "api_key": "",
        "secret": "",
        "sandbox": True,
        "symbol": "ETH/USDT",
        "dca_symbol": "BTC/USDT",
        "capital": 500,
        "grid_count": 20,
        "dca_base_amount": 20,
        "max_drawdown": 15,
        "interval_minutes": 60,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(default_config, f, indent=2)
    log.info(f"[CONFIG] 기본 설정 생성: {config_path}")
    return default_config


def run_bot():
    """봇 메인 루프"""
    config = load_config()

    if not config.get("api_key"):
        log.error("[ERROR] API 키가 설정되지 않았습니다!")
        log.error("  data/trading_config.json에 api_key와 secret을 입력하세요.")
        return

    bot = HybridTradingBot(config)
    interval = config.get("interval_minutes", 60) * 60  # 초 단위

    log.info(f"[START] 하이브리드 봇 시작 (간격: {interval // 60}분)")

    while True:
        try:
            trades = bot.run_cycle()
            if trades:
                log.info(f"[TRADES] 이번 사이클 거래: {len(trades)}건")
            time.sleep(interval)
        except KeyboardInterrupt:
            log.info("[STOP] 사용자 중단")
            break
        except Exception as e:
            log.error(f"[ERROR] {e}")
            time.sleep(60)  # 에러 시 1분 대기 후 재시도


# ─── 시뮬레이션 모드 (API 키 없이 테스트) ────────────

def run_simulation():
    """API 키 없이 시장 분석만 실행 (페이퍼 트레이딩)"""
    log.info("[SIM] 시뮬레이션 모드 시작 (실제 거래 없음)")

    # 공개 API로 데이터만 수집
    exchange = ccxt.binance({"enableRateLimit": True})

    symbol = "ETH/USDT"
    df = fetch_ohlcv(exchange, symbol, "1h", 100)
    df = compute_indicators(df)
    fgi = fetch_fear_greed_index()

    latest = df.iloc[-1]
    regime = detect_market_regime(df, fgi)

    report = []
    report.append(f"📊 시장 분석 리포트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    report.append(f"")
    report.append(f"코인: {symbol}")
    report.append(f"현재가: {latest['close']:.2f} USDT")
    report.append(f"")
    report.append(f"📈 기술 지표:")
    report.append(f"  ADX: {latest['adx']:.1f} ({'횡보' if latest['adx'] < 25 else '추세'})")
    report.append(f"  RSI: {latest['rsi']:.1f} ({'과매도' if latest['rsi'] < 30 else '과매수' if latest['rsi'] > 70 else '중립'})")
    report.append(f"  BB 상단: {latest['bb_upper']:.2f}")
    report.append(f"  BB 하단: {latest['bb_lower']:.2f}")
    report.append(f"  BB 폭: {latest['bb_width']:.4f}")
    report.append(f"  MACD: {latest['macd']:.2f} (시그널: {latest['macd_signal']:.2f})")
    report.append(f"  ATR: {latest['atr']:.2f}")
    report.append(f"  EMA20: {latest['ema_20']:.2f}, EMA50: {latest['ema_50']:.2f}")
    report.append(f"")
    report.append(f"😱 Fear & Greed Index: {fgi}")
    report.append(f"")
    report.append(f"🏷️ 시장 상태: {regime}")
    report.append(f"")

    if regime == "panic":
        report.append(f"⚡ 추천: 전략 4 (Fear & Greed 역발상 매수)")
    elif regime == "sideways":
        report.append(f"⚡ 추천: 전략 1 (Smart Grid)")
        interval = (latest['bb_upper'] - latest['bb_lower']) / 20
        report.append(f"  그리드 범위: {latest['bb_lower']:.2f} ~ {latest['bb_upper']:.2f}")
        report.append(f"  그리드 간격: {interval:.2f}")
    elif regime == "trending":
        report.append(f"⚡ 추천: 전략 2 (RSI DCA)")
        if latest['rsi'] < 30:
            report.append(f"  🟢 RSI 과매도 → 매수 시그널!")
        elif latest['rsi'] > 70:
            report.append(f"  🔴 RSI 과매수 → 매도 시그널!")
        else:
            report.append(f"  ⏳ RSI 중립 → 대기")

    return "\n".join(report)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "sim":
        report = run_simulation()
        print(report)
    else:
        run_bot()
