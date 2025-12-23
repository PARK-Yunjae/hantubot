# hantubot_prod/hantubot/gui/main_window.py
import sys
import logging
import os
from dotenv import load_dotenv

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QRadioButton, QGroupBox, QCheckBox, QTextEdit, QLabel
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

# --- Import Core Components ---
# This assumes the project root is in PYTHONPATH, which run.py will handle.
from hantubot.utils.config_loader import load_config_with_env
from hantubot.core.clock import MarketClock
from hantubot.reporting.logger import get_logger
from hantubot.reporting.notifier import Notifier
from hantubot.execution.broker import Broker
from hantubot.core.portfolio import Portfolio
from hantubot.execution.order_manager import OrderManager
from hantubot.core.engine import TradingEngine

# --- Qt Logging Handler ---
class QtLogHandler(logging.Handler):
    """
    A logging handler that emits a Qt signal for each log record.
    """
    class Emitter(QObject):
        log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.emitter = self.Emitter()

    def emit(self, record):
        msg = self.format(record)
        self.emitter.log_signal.emit(msg)

# --- Engine Worker ---
class EngineWorker(QObject):
    """
    Worker object that runs the TradingEngine in a separate thread.
    """
    finished = Signal()
    engine_initialized = Signal(object)

    def __init__(self):
        super().__init__()
        self.engine = None
        
    def run(self):
        """Initializes and starts the trading engine."""
        try:
            main_logger = get_logger("hantubot.worker")
            main_logger.info("Hantubot GUI: Initializing engine in worker thread...")
            
            # Load .env variables from the 'configs' directory
            load_dotenv(dotenv_path=os.path.join(os.getcwd(), 'configs', '.env'))

            config_path = os.path.join(os.getcwd(), 'configs', 'config.yaml')
            config = load_config_with_env(config_path)

            is_mock = config.get('mode', 'mock').lower() == 'mock'
            market_clock = MarketClock(config_path=config_path)
            notifier = Notifier(config_path=config_path)
            broker = Broker(config=config, is_mock=is_mock)
            
            balance_data = broker.get_balance()
            summary = balance_data.get('summary', {})
            positions = balance_data.get('positions', [])

            initial_cash = summary.get('cash', 0)
            if initial_cash == 0 and not positions:
                initial_cash = 10_000_000 if is_mock else 0 # Set default cash only if no positions and no cash

            portfolio = Portfolio(initial_cash=initial_cash, initial_positions=positions)
            order_manager = OrderManager(broker=broker, portfolio=portfolio, clock=market_clock)

            self.engine = TradingEngine(
                config=config, market_clock=market_clock, broker=broker,
                portfolio=portfolio, order_manager=order_manager, notifier=notifier
            )
            
            self.engine_initialized.emit(self.engine)
            main_logger.info("TradingEngine initialized in worker. Starting main loop...")
            self.engine.start() # This blocks until the engine is stopped.
            
        except Exception as e:
            get_logger("hantubot.worker").critical(f"Unhandled exception in EngineWorker: {e}", exc_info=True)
            
        finally:
            self.finished.emit()

    def stop(self):
        if self.engine:
            self.engine.stop()

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("한투봇 컨트롤러")
        self.setGeometry(100, 100, 800, 600)

        self.worker_thread = None
        self.engine_worker = None
        self.config = None
        
        self._setup_ui()
        self._connect_signals()
        self._configure_logging()
        self._load_initial_config()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(250)
        
        engine_group = QGroupBox("엔진 제어")
        engine_layout = QVBoxLayout()
        self.btn_start = QPushButton("엔진 시작")
        self.btn_stop = QPushButton("엔진 정지")
        self.btn_stop.setEnabled(False)
        engine_layout.addWidget(self.btn_start)
        engine_layout.addWidget(self.btn_stop)
        engine_group.setLayout(engine_layout)

        mode_group = QGroupBox("운영 모드")
        mode_layout = QVBoxLayout()
        self.radio_mock = QRadioButton("모의 투자")
        self.radio_live = QRadioButton("실전 투자")
        mode_layout.addWidget(self.radio_mock)
        mode_layout.addWidget(self.radio_live)
        mode_group.setLayout(mode_layout)

        self.strategy_group = QGroupBox("활성 전략")
        self.strategy_layout = QVBoxLayout()
        self.strategy_group.setLayout(self.strategy_layout)

        left_layout.addWidget(engine_group)
        left_layout.addWidget(mode_group)
        left_layout.addWidget(self.strategy_group)
        left_layout.addStretch(1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        log_label = QLabel("실시간 로그")
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        right_layout.addWidget(log_label)
        right_layout.addWidget(self.log_text_edit)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        
    def _connect_signals(self):
        self.btn_start.clicked.connect(self.start_engine)
        self.btn_stop.clicked.connect(self.stop_engine)

    def _configure_logging(self):
        """Configure logging to redirect to the GUI."""
        self.log_handler = QtLogHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.log_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)
        
        self.log_handler.emitter.log_signal.connect(self.append_log)

    def _load_initial_config(self):
        """Load config to set up the UI before the engine starts."""
        try:
            config_path = os.path.join(os.getcwd(), 'configs', 'config.yaml')
            self.config = load_config_with_env(config_path)

            is_mock = self.config.get('mode', 'mock').lower() == 'mock'
            self.radio_mock.setChecked(is_mock)
            self.radio_live.setChecked(not is_mock)
            self.radio_mock.setEnabled(False)
            self.radio_live.setEnabled(False)

            for strat_name in self.config.get('active_strategies', []):
                checkbox = QCheckBox(strat_name)
                checkbox.setChecked(True)
                self.strategy_layout.addWidget(checkbox)

        except FileNotFoundError:
            self.append_log(f"CRITICAL: Configuration file not found at {config_path}")
        except Exception as e:
            self.append_log(f"CRITICAL: Error loading initial config: {e}")

    def append_log(self, message):
        self.log_text_edit.append(message)
        self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())

    def start_engine(self):
        self.append_log("Starting engine in a new thread...")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.worker_thread = QThread()
        self.engine_worker = EngineWorker()
        self.engine_worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.engine_worker.run)
        self.engine_worker.finished.connect(self.on_engine_finished)
        
        self.worker_thread.start()

    def stop_engine(self):
        self.append_log("Sending stop signal to engine...")
        if self.engine_worker:
            self.engine_worker.stop()

    def on_engine_finished(self):
        self.append_log("Engine has stopped.")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.engine_worker = None

    def closeEvent(self, event):
        """Ensure engine stops when the window is closed."""
        self.append_log("Main window is closing, stopping engine...")
        self.stop_engine()
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
        super().closeEvent(event)