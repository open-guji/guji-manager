# guji-manager Wiki

> **本 Wiki 对应 guji-manager v0.5**（2026-11-21 按 0.5.0 重改：网站票改读中心库收件箱、新增「数据库表一览」）。
> 版本号差了一个 MINOR（比如代码到了 0.5.x），说明这里可能过时，以仓里 [doc/](https://github.com/open-guji/guji-manager/blob/dev/doc/README.md) 为准，并按[维护规矩](版本与Wiki维护)重改。

**guji-manager** 是开源古籍整理流水线的「管家」：新建工作区、登记和取原图、跑批派单、推拉中心库、出线上待审单、收读者投票、冻结发布——一切和外界打交道的事。
识别算法本身（切分、识别、定字）在 [open-guji-cv](https://github.com/open-guji/open-guji-cv)。

![两个仓怎么分工](images/boundary.png)

一句话分界：**会改变识别产物字节的在 cv，其余在 manager**。所以改 manager 不用给 cv 发版，也不会让任何一册的产物过期。0.4 起拆分完成：cv 里已没有 manager 一侧的代码，`guji` 里整理流程的命令都由 manager 提供，cv 只留识别本身的（`pipeline`／`step`／`status` 等）。

## 先看哪页

![四大步](images/stages.png)

整理一套书分四大步，侧栏按这四步排：[第一步 新书启动](第一步-新书启动) → [第二步 迭代](第二步-迭代) → [第三步 AI 文意判字、标点、专名](第三步-AI文意判字标点专名) → [第四步 网站人审与版本迭代](第四步-网站人审与版本迭代)。新来的先看 [系统全景](系统全景) 和 [一部书怎么走完](一部书怎么走完)；装环境看 [安装与环境](安装与环境)；查表看 [数据库表一览](数据库表一览)。

## Wiki 和 doc/ 的分工

- **Wiki（这里）**：看图懂系统。每页先图后文，讲「是什么、长什么样、为什么」，末尾链到 doc/ 细篇。
- **仓里 [doc/](https://github.com/open-guji/guji-manager/blob/dev/doc/README.md)**：干活时查的操作手册——每步命令、验收标准、常见坑。命令细节以 doc/ 为准。

## 维护规矩（重要）

1. 平时出 PATCH 版不要求改 Wiki。
2. **每升一次 MINOR 版，必须整体重改一遍 Wiki**：列出上个 MINOR 以来的全部 PATCH，归纳涉及了哪些功能，逐页对照改、该补的补页、截图该重截的重截，再把本页顶上的「对应 vX.Y」改掉。
3. MINOR 发版的 PR 里写一行「Wiki 已按 vX.Y 重改」才算发完。

细则见 [版本与 Wiki 维护](版本与Wiki维护)。

## 怎么改这个 Wiki

Wiki 源文件在主仓 [`wiki/`](https://github.com/open-guji/guji-manager/blob/dev/wiki) 目录（图在 `wiki/images/`），改它走 PR；合进 main 后由 Action `wiki-sync` 自动同步到这里。**不要直接在网页上改 Wiki**，下次同步会被覆盖。
