from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from scraper.worker import ImageScraperThread
from scraper.dynamic_extractor import DynamicImageExtractor

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.current_mode = "static"
        self.dynamic_login_pending = False
        self.pending_page_url = ""
        self.pending_save_dir = ""
        self.dynamic_extractor = None
        self.init_ui()
        self.current_mode = "static"

    def init_ui(self):
        self.setWindowTitle("网页图片抓取工具")
        self.setFixedSize(860, 620)

        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #eef0f3;
            }
            QWidget {
                font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            }
            QLineEdit {
                border: 2px solid #d8dde6;
                border-radius: 16px;
                padding: 14px 18px;
                font-size: 18px;
                background: white;
                color: #4a5568;
            }
            QLineEdit:focus {
                border-color: #4a90e2;
            }
            QPushButton {
                background-color: #1f7ae0;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 22px;
                font-weight: 600;
                padding: 18px 28px;
            }
            QPushButton:hover {
                background-color: #176ccc;
            }
            QPushButton:disabled {
                background-color: #8db8ef;
                color: #edf4ff;
            }
            QProgressBar {
                border: none;
                background: #dfe3e8;
                border-radius: 6px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #1f7ae0;
                border-radius: 6px;
            }
            QLabel {
                color: #5a6472;
            }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(70, 20, 70, 20)
        outer_layout.setAlignment(Qt.AlignTop)
        outer_layout.setSpacing(20)

        self.mode_button = QPushButton("当前模式：静态抓取")
        self.mode_button.setFixedHeight(64)
        self.mode_button.clicked.connect(self.toggle_mode)
        outer_layout.addWidget(self.mode_button)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入网址，例如：https://example.com")
        self.url_input.setMinimumHeight(58)
        outer_layout.addWidget(self.url_input)

        self.status_label = QLabel("0% 正在准备...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        outer_layout.addSpacing(8)
        outer_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(12)
        outer_layout.addWidget(self.progress_bar)

        outer_layout.addSpacing(30)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.start_button = QPushButton("开始抓取")
        self.start_button.setFixedSize(360, 92)
        self.start_button.clicked.connect(self.choose_folder_and_start)
        button_row.addWidget(self.start_button)

        button_row.addStretch()
        outer_layout.addLayout(button_row)

    def toggle_mode(self):
        if self.current_mode == "static":
            self.current_mode = "dynamic"
            self.mode_button.setText("当前模式：动态抓取")
            QMessageBox.information(self, "提示", "动态模式将打开浏览器，请在浏览器中完成登录后等待页面加载。")
        else:
            self.current_mode = "static"
            self.mode_button.setText("当前模式：静态抓取")

    def choose_folder_and_start(self):
        # 动态模式：第二次点击，表示“我已登录，开始抓取”
        if self.current_mode == "dynamic" and self.dynamic_login_pending:
            try:
                self.progress_bar.setValue(0)
                self.start_button.setEnabled(False)
                self.url_input.setEnabled(False)
                self.mode_button.setEnabled(False)

                self.status_label.setText("正在从当前页面提取图片链接...")

                image_urls = self.dynamic_extractor.extract_from_current_page(self.pending_page_url)

                self.worker = ImageScraperThread(
                    self.pending_page_url,
                    self.pending_save_dir,
                    mode="dynamic",
                    image_urls=image_urls,
                )
                self.worker.progress_changed.connect(self.on_progress_changed)
                self.worker.status_changed.connect(self.on_status_changed)
                self.worker.finished_ok.connect(self.on_finished_ok)
                self.worker.failed.connect(self.on_failed)
                self.worker.start()
            except Exception as exc:
                self.start_button.setEnabled(True)
                self.url_input.setEnabled(True)
                self.mode_button.setEnabled(True)
                QMessageBox.critical(self, "错误", str(exc))
            return

        page_url = self.url_input.text().strip()
        if not page_url:
            QMessageBox.warning(self, "提示", "请先输入网页地址。")
            return

        if not page_url.startswith(("http://", "https://")):
            page_url = "https://" + page_url
            self.url_input.setText(page_url)

        save_dir = QFileDialog.getExistingDirectory(self, "选择图片保存文件夹")
        if not save_dir:
            return

        # 动态模式：第一次点击，先打开浏览器等待登录
        if self.current_mode == "dynamic":
            try:
                self.dynamic_extractor = DynamicImageExtractor()
                self.dynamic_extractor.open_page(page_url)

                self.pending_page_url = page_url
                self.pending_save_dir = save_dir
                self.dynamic_login_pending = True

                self.start_button.setText("我已登录，开始抓取")
                self.url_input.setEnabled(False)
                self.mode_button.setEnabled(False)
                QMessageBox.information(
                    self,
                    "动态模式",
                    "浏览器已打开，请先在浏览器中完成登录，并停留在你要抓取的页面，然后回来点击“我已登录，开始抓取”。"
                )
            except Exception as exc:
                if self.dynamic_extractor:
                    self.dynamic_extractor.close()
                    self.dynamic_extractor = None
                QMessageBox.critical(self, "错误", str(exc))
            return

        # 静态模式：直接抓取
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(False)
        self.url_input.setEnabled(False)
        self.mode_button.setEnabled(False)

        self.worker = ImageScraperThread(page_url, save_dir, mode="static")
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.status_changed.connect(self.on_status_changed)
        self.worker.finished_ok.connect(self.on_finished_ok)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_progress_changed(self, value: int):
        self.progress_bar.setValue(value)

    def on_status_changed(self, text: str):
        current = self.progress_bar.value()
        if text.startswith("正在下载") or text.startswith("正在获取") or text.startswith("共发现"):
            self.status_label.setText(f"{current}% {text}")
        else:
            self.status_label.setText(text)

    def on_finished_ok(self, message: str):
        self.start_button.setEnabled(True)
        self.url_input.setEnabled(True)
        self.mode_button.setEnabled(True)

        if self.current_mode == "dynamic":
            self.start_button.setText("开始抓取")
            self.dynamic_login_pending = False
            self.pending_page_url = ""
            self.pending_save_dir = ""
            if self.dynamic_extractor:
                self.dynamic_extractor.close()
                self.dynamic_extractor = None

        self.status_label.setText("100% 抓取完成")
        QMessageBox.information(self, "完成", message)

    def on_failed(self, error_message: str):
        self.start_button.setEnabled(True)
        self.url_input.setEnabled(True)
        self.mode_button.setEnabled(True)

        if self.current_mode == "dynamic":
            self.start_button.setText("开始抓取")
            self.dynamic_login_pending = False
            self.pending_page_url = ""
            self.pending_save_dir = ""
            if self.dynamic_extractor:
                self.dynamic_extractor.close()
                self.dynamic_extractor = None

        self.status_label.setText("抓取失败")
        QMessageBox.critical(self, "错误", error_message)
    
    def toggle_mode(self):
        if self.dynamic_login_pending:
            QMessageBox.warning(self, "提示", "当前正在等待动态模式登录完成，请先完成或结束本次操作。")
            return

        if self.current_mode == "static":
            self.current_mode = "dynamic"
            self.mode_button.setText("当前模式：动态抓取")
        else:
            self.current_mode = "static"
            self.mode_button.setText("当前模式：静态抓取")