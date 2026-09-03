# Image Prompt Library

[![CI](https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/ci.yml)
[![GitHub Pages demo](https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/release/EddieTYP/image-prompt-library?label=release)](https://github.com/EddieTYP/image-prompt-library/releases/latest)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

[English](README.md) · [繁體中文](README_zh-TW.md) · **简体中文**

**Image Prompt Library** 是一个本地优先的图片与提示词资料库。把图片、prompt、来源和备注一起保存，通过 collection、tag 和搜索整理，方便之后找回及重用。

资料保存在本地 SQLite 和图片文件中。保存、搜索和整理不需要账号。你也可以选择连接 ChatGPT 或 Grok 来生成图片及建议标题；这些请求会由服务供应商的服务器处理，并非在你的电脑上运行 AI 模型。

![本地 Library 的图片与 prompt 卡片](docs/assets/screenshots/local-app-library-overview.jpg)

*本地 app 已加载可选示例资料。新安装的资料库默认是空的。*

## 版本状态

`v0.11.0` 是当前稳定版本，可从 [GitHub Latest](https://github.com/EddieTYP/image-prompt-library/releases/latest) 下载。新增 **Grok 图片生成与标题建议**、多图卡片，以及可搜索的批量 Tag 和 Move 菜单。完整变更见 [v0.11.0 更新说明](docs/releases/v0.11.0.md)。

## 快速开始

### Windows

需要 Windows 10/11、PowerShell 5.1+ 及 **Python 3.10+**。请先安装 Python；安装程序不会代为安装。

```powershell
irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 | iex
```

安装后会在后台启动 app 并打开浏览器。使用 `image-prompt-library stop` 停止。

### macOS、Linux 和 WSL 2

需要 **Python 3.10+** 和 `curl`。使用 release 安装不需要 Node.js。

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library start
```

保持终端打开，并浏览 [http://127.0.0.1:8000](http://127.0.0.1:8000)。在该终端按 `Ctrl-C` 可停止 server。

如希望先查看安装程序再执行，或需要更新、回退旧版、卸载，请看[安装说明](docs/INSTALLATION.md)。启动有问题时，可先执行 `image-prompt-library status` 和 `image-prompt-library doctor`，再参考[故障排查](docs/TROUBLESHOOTING.md)。

### 保存第一个 prompt

新资料库默认是空的。选择 **+ Add**，加入图片、prompt 和标题后保存。Collection、tag、备注和来源链接均为选填。

想先浏览示例，可选择导入一个 sample pack：

```bash
image-prompt-library sample-data en       # 英文 collection 名称
image-prompt-library sample-data zh_hans  # 简体中文 collection 名称
image-prompt-library sample-data zh_hant  # 繁体中文 collection 名称
```

只需执行偏好语言的指令。原始标题、prompt 及已有语言版本会保留，不会全部重新翻译。另有较大的繁中示例包：

```bash
image-prompt-library sample-data zh_hant awesome-gpt-image-2
```

## 浏览与整理

- **Explore** 按 collection 展示图片；**Library** 提供完整卡片列表及编辑工具。
- 原始 prompt 和翻译可放在同一卡片，切换语言版本后即可阅读或复制。
- 搜索标题、prompt、tag、collection、来源及备注，亦可组合 `tag:portrait`、`collection:architecture`、`sort:title` 等结构化筛选。
- 选择多张卡片后，可批量加 tag、移动、收藏、封存或删除。**Tag** 会建议现有标签；**Move** 可搜索 collection，不用输入完全相同的名称。
- 可在同一卡片保存多张图片。在 **Edit** 选择封面、调整顺序、更改结果图／参考图角色，或只删除其中一张图片。

![按 collection 浏览的 Explore 画面](docs/assets/screenshots/local-app-explore.jpg)

*Explore 用于浏览 collection；Library 用于管理个别卡片。*

![卡片详情：图片、prompt 语言版本、标签和来源](docs/assets/screenshots/local-app-detail.jpg)

*同一卡片集中保存图片、prompt 和来源。新生成的图片亦会保留 provider 及 model 资料。*

## 使用 ChatGPT 或 Grok 生成图片

图片生成是可选功能，需要本地安装及具相应权限的 provider 账号。**Grok OAuth 属实验功能。** 使用权限、配额和费用由 provider 决定；成功连接不代表免费或无限使用。这两种 OAuth 连接不需要输入 API key。

1. 打开 **Config → Providers**，选择 **ChatGPT / Codex OAuth** 或 **Grok OAuth**，在浏览器完成授权。如有提示，回到 app 按 **Check authorization**。
2. 选择 **Default AI provider**。偏好会保存在目前的浏览器；生成时仍可暂时转用另一个 provider，不影响默认。
3. 打开 **Generate**，输入 prompt，可选择加入参考图。Prompt 可使用 `{{主体}}` 等变量，生成前先填入内容。
4. 选择可用的比例、质量及其他选项。一次生成 1 张或一组 3、5、10 张，再从 **Work queue** 查看结果。
5. 选择 **Save as new item**，或附加至未经修改的来源卡片。查看同一组结果时，之后的图片可加入第一张结果创建的卡片，集中在同一详情窗口浏览。

Grok 使用 `grok-imagine-image-2.0`，提供 Low／Medium 质量、1K／2K 分辨率，最多三张参考图。ChatGPT 最多支持四张参考图，另有自己的 model 及质量选项。切换 provider 后会显示相应选项。

![生成窗口的 provider 菜单已选择 Grok](docs/assets/screenshots/generation-grok-provider.png)

*在生成窗口选择本次使用的 provider，不会改变 Config 中的默认值。*

### 建议标题

在 **Add**、**Edit** 或生成结果的保存表单按 **Suggest title**，即可根据 prompt 文字取得短标题。先查看建议，再按 **Use title** 应用；原标题不会自动被覆盖。

一般新增／编辑使用默认 provider；生成结果会使用生成该图的 provider，并显示 **via ChatGPT** 或 **via Grok**。如该 provider 已断线，app 会要求重新连接，不会静默把 prompt 送到另一间服务。

详细连接方法、参考图限制及结果处理，请看[生成指南](docs/GENERATION.md)。

## 线上只读 demo

[打开 demo](https://eddietyp.github.io/image-prompt-library/)，不用安装即可浏览 collections、搜索示例及复制公开 prompt。

![线上只读 demo 的 Explore 画面](docs/assets/screenshots/public-demo-explore.png)

*线上 demo 使用公开示例资料。编辑、私人资料库管理及图片生成需要本地安装。*

## Sample data 与 attribution

Demo 及可选示例包保留来源链接和授权信息。当中的 prompt 和图片并非 Image Prompt Library 原创内容。

| 来源 | 授权 | 示例包 |
| --- | --- | --- |
| [wuyoscar/gpt_image_2_skill](https://github.com/wuyoscar/gpt_image_2_skill) | CC BY 4.0 | Starter pack |
| [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) | MIT | 较大的 prompt／图片示例库 |

示例包详情及校验码见 [sample-data/README.md](sample-data/README.md)。

## 隐私

- 私人 prompt／图片资料库留在你的电脑，没有托管用户资料库或内建云端同步。
- 生成图片时，输入的 prompt 和所选参考图会传送至你选择的 provider。建议标题只传送 prompt 文字，不会传送图片、现有标题、tag 或备注。
- Provider 凭据与资料库分开保存，不会包含在可移植备份或示例导出中。
- App 默认只监听 `127.0.0.1`。除非了解访问风险，否则不要开放至网络。

## 文件

- [安装与更新](docs/INSTALLATION.md)
- [图片生成及建议标题](docs/GENERATION.md)
- [备份与还原](docs/BACKUP_AND_RESTORE.md)
- [故障排查](docs/TROUBLESHOOTING.md)
- [开发环境](docs/DEVELOPMENT.md)及[参与开发](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)

## 授权

App 代码采用 **AGPL-3.0-or-later**，详见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。示例数据和第三方资产使用上表所列的独立授权。

如需在 AGPL 以外的条款下使用，可联络维护者洽谈商业授权。
