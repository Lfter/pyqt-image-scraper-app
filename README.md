# PyQt Image Scraper App

一个使用 PyQt 开发的网页图片抓取工具。

## 功能
- 输入网页地址
- 选择图片保存目录
- 抓取网页图片并分类保存
- 显示抓取进度
- 支持静态抓取和需要登录后的动态抓取

## 运行方式
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

兼容入口 `Pyqt Image Scraper App.py` 仍然保留，但内部已经转发到 `main.py`，后续只需要维护一套实现。

## 动态模式
动态抓取依赖 Playwright。首次安装依赖后，还需要执行：

```bash
playwright install
```

## 运行测试
```bash
python -m unittest discover -s tests -v
```
