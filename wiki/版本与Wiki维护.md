# 版本与 Wiki 维护

## 版本号

- guji-manager 用 `m-vX.Y.Z` tag，**不钉到册、不进产物指纹**，所以发版不会让任何册过期。
- PATCH（Z）：修 bug、小功能、文档。
- MINOR（Y）：一批功能搬来或新增、命令有变。MINOR 升版要用户点头。
- 每版改了什么写在 [CHANGELOG.md](https://github.com/open-guji/guji-manager/blob/main/CHANGELOG.md)。

## Wiki 什么时候改

![Wiki 什么时候改](images/wikirule.png)

**平时不追着改。** 每个 PATCH 都改 Wiki 太累，也容易忘；Wiki 写的是「看图懂系统」，PATCH 一般动不到这一层。

**每升一次 MINOR，必须整体重改一遍：**

1. 列出上一个 MINOR 以来的全部 PATCH：看 CHANGELOG，和 `git log m-vX.(Y-1).0..HEAD --oneline`；
2. 归纳这些 PATCH 涉及了哪些功能（新命令、搬来的模块、改了的流程）；
3. 逐页对照：过时的改，新功能补页或补段，截图该重截的重截（截图里有令牌、内部地址的要打码）；
4. 首页顶上的「本 Wiki 对应 m-vX.Y」改成新版本；
5. 在本页下面「改版记录」加一段；
6. MINOR 发版的 PR 里写一行「Wiki 已按 m-vX.Y 重改」，才算发完。

## 怎么改

- 源文件在主仓 `wiki/`，图在 `wiki/images/`，走 PR、和代码一起审。
- 合进 main 后 Action `wiki-sync` 自动把 `wiki/` 整个同步到 GitHub Wiki。**别在 Wiki 网页上直接改**，会被下次同步覆盖。
- 截图尽量用真数据（殿本总目 vol03 是现成的演示册）；示意图的源 HTML 在 `wiki/images/src/`，改完用 Playwright 重新截。

## 改版记录

| 日期 | 对应版本 | 改了什么 |
|---|---|---|
| 2026-11-03 | m-v0.2（0.2.0） | 首版：13 页。基线功能：pipeline 调用与契约检查、opinions、source、cellvotes、freeze、online_lists、review_triage、pending-stats、central-gc；拆分进行到 P2 第二批。 |
