import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trading import PaperTradingEngine


class PaperTradingEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = PaperTradingEngine(data_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_account_uses_200_usdt(self):
        status = self.engine.status()
        self.assertEqual(status['config']['mode'], 'paper')
        self.assertAlmostEqual(status['state']['cash'], 200.0)
        self.assertAlmostEqual(status['equity'], 200.0)

    def test_paper_buy_and_sell_include_fees(self):
        config = self.engine.load_config()
        state = self.engine.load_state()
        self.engine._execute_buy(state, config, price=100.0, rsi=55.0)

        bought = self.engine.load_state()
        self.assertIsNotNone(bought['position'])
        self.assertAlmostEqual(bought['position']['notional'], 50.0)
        self.assertAlmostEqual(bought['cash'], 149.9)

        self.engine._execute_sell(
            bought, config, price=103.0, reason='测试止盈'
        )
        sold = self.engine.load_state()
        self.assertIsNone(sold['position'])
        self.assertAlmostEqual(sold['realized_pnl'], 1.297, places=3)
        self.assertAlmostEqual(sold['cash'], 201.297, places=3)
        self.assertEqual(len(self.engine.load_history()), 2)

    def test_indicator_calculation(self):
        frame = pd.DataFrame({
            'timestamp': list(range(60)),
            'open': list(range(60)),
            'high': list(range(60)),
            'low': list(range(60)),
            'close': [100 + i * 0.1 for i in range(60)],
            'volume': [1] * 60,
        })
        result = self.engine._add_indicators(frame, self.engine.load_config())
        self.assertIn('ema_fast', result.columns)
        self.assertIn('ema_slow', result.columns)
        self.assertIn('rsi', result.columns)
        self.assertTrue(result['rsi'].between(0, 100).all())


if __name__ == '__main__':
    unittest.main()
