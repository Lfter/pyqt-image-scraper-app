# PyQt Image Scraper App

一个使用 PyQt 开发的网页图片抓取工具。

## 功能
- 输入网页地址
- 选择图片保存目录
- 抓取网页图片并分类保存
- 显示抓取进度
- 支持静态抓取和需要登录后的动态抓取
- 可选为 WEBP / AVIF / TIFF / BMP 自动生成更通用的兼容格式副本
- 可将 SVG 额外渲染为 PNG 兼容副本

## 运行方式
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

默认会保留原图；如果启用了“自动生成兼容格式副本”，程序会为可转码图片额外生成一份 `*_compatible.png` 或 `*_compatible.jpg`。
其中 SVG 会直接渲染为 PNG，AVIF 会通过 `pillow-avif-plugin` 进行解码后再转为更通用的格式。

程序现在会尽量优先抓取原图：
- 提取阶段会优先保留 `data-full`、`data-original`、大图 `srcset` 等更像原图的链接。
- 下载阶段会自动尝试把常见缩略图 URL 还原成原图 URL。
- 动态模式会把浏览器中的登录 Cookie 同步到下载会话里，减少拿到占位图或低清图的情况。

## 动态模式
动态抓取依赖 Playwright。首次安装依赖后，还需要执行：

```bash
playwright install
```

## 运行测试
```bash
python -m unittest discover -s tests -v
```
