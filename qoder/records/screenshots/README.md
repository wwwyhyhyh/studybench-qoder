# 站点截图（提交材料「演示」用）

| 文件 | 说明 | 采集方式 |
| --- | --- | --- |
| `site-1280.png` | 桌面端首屏（1280×2600 长图） | Chrome headless `--window-size=1280,2600` |
| `site-375.png` | 移动端（375 CSS px 视口，验证无横向溢出） | CDP `Emulation.setDeviceMetricsOverride{width:375,mobile:true}` + `Page.captureScreenshot` |
| `site-tryit.png` | **试用区真实检索结果**：输入「分光计调到什么程度算调好」，浏览器端本地打分，top-1 = `物理实验/分光计与三棱镜顶角.md:23-25`，得分 36.193389（与 Python 引擎同分），命中 19/96 块、耗时 7 ms | 同上，提交查询后截取 `#try` 区块 |

复现要点：

- Chrome headless 在 Windows 上**最小窗口宽度为 500 px**，用 `--window-size=390` 截图会得到「被裁掉右边」的假象；
  测移动端必须用 CDP 的 `Emulation.setDeviceMetricsOverride`（`site-375.png` 即此法）。
  实测 375 px 视口下 `scrollWidth == clientWidth == 375`，唯一超出视口的元素是终端实录块内的长行，
  它自带 `overflow-x:auto`，属设计允许的内部滚动。
- 所有截图都是真实渲染，不是手绘/合成；站点零外链，断网可打开。
