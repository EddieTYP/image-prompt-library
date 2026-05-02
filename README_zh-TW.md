# Image Prompt Library

[![CI](https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/ci.yml)
[![GitHub Pages demo](https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/tag/EddieTYP/image-prompt-library?sort=semver&label=release)](https://github.com/EddieTYP/image-prompt-library/releases/tag/v0.6.5-beta)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

<p align="center">
  <strong>語言：</strong>
  <a href="README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="README_zh-CN.md">簡體中文</a>
</p>

**Image Prompt Library** 是一個本地優先的圖片與提示詞收藏庫。它幫你把好用的生成圖片、背後的 prompt、來源和備註一起保存起來，再用 collection、tag 和搜尋慢慢整理成自己的視覺資料庫。

你的私人 library 會留在自己的電腦：本地 SQLite、本地圖片檔案，沒有 hosted database，沒有內建雲端同步，也不需要註冊帳號。

## 為甚麼做這個

生成圖片多了之後，最麻煩的往往不是再生一張，而是找回之前哪個 prompt 好用、哪張圖適合參考、當時用了甚麼來源和變體。

Image Prompt Library 就是為這件事而做：把分散在聊天紀錄、資料夾和截圖裡的 prompt/image references，整理成一個可瀏覽、可搜尋、可追溯來源的本地 library。你可以把它當成自己的 prompt catalogue，也可以先用公開 demo 逛一圈 sample gallery。

**線上唯讀 demo：** <https://eddietyp.github.io/image-prompt-library/>

公開 demo 收錄了 **533 個 prompt/image references**，整理自兩個慷慨開放的上游 gallery：[`wuyoscar/gpt_image_2_skill`](https://github.com/wuyoscar/gpt_image_2_skill)（**CC BY 4.0**）和 [`freestylefly/awesome-gpt-image-2`](https://github.com/freestylefly/awesome-gpt-image-2)（**MIT**）。內容涵蓋 UI 與介面、海報與排版、商品與電商、圖表與資訊可視化、技術圖解、攝影寫實、角色人物、建築空間、敘事場景和插畫風格。每個案例都以圖片卡片呈現；如來源資料有提供，也會保留英文、繁體中文、簡體中文的 prompt variant。

<p align="center">
  <img src="docs/assets/screenshots/public-demo-v0.6-533-references.png" alt="Image Prompt Library public demo showing 533 prompt references" width="100%" />
</p>

你可以用 demo 快速找靈感、看 prompt 結構、複製公開 sample prompt，或者比較不同寫法對出圖效果的影響。GitHub Pages demo 是靜態唯讀版本；新增、編輯、私人 library 管理和圖片生成，都在本地安裝版使用。

目前公開 beta：[`v0.6.5-beta`](https://github.com/EddieTYP/image-prompt-library/releases/tag/v0.6.5-beta)。這版更新了 `gpt_image_2_skill` 和 `awesome-gpt-image-2` 的公開 sample metadata，修正雙語 prompt variants，加入 demo 用的本地化 card titles，並保留 v0.6 beta 系列的本地生成、installer、update 和 rollback workflow。

## 快速開始

一般 release 安裝只需要 **Python 3.10+** 和 `curl`，不需要 Node.js。

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library start
```

`image-prompt-library start` 會在目前 terminal 啟動本地 server。保持 terminal 開住，然後用瀏覽器打開 <http://127.0.0.1:8000/>。要關閉 server，就在同一個 terminal 按 `Ctrl-C`。

可選：如果想在新的本地 library 先放一批 demo references，可以匯入 starter sample pack。

```bash
image-prompt-library sample-data en       # English collection names
image-prompt-library sample-data zh_hans  # Simplified Chinese collection names
image-prompt-library sample-data zh_hant  # Traditional Chinese collection names
```

Starter sample pack 可以用英文、簡體中文或繁體中文的 collection name 匯入。這不是把所有原始 prompt/title 全部翻譯一次；sample 仍會保留來源 title、prompt 和已有的 prompt variants，語言選項主要影響匯入後的 collection label 和 sample-pack metadata。

如果想匯入較大的繁中 `awesome-gpt-image-2` sample pack：

```bash
image-prompt-library sample-data zh_hant awesome-gpt-image-2
```

更新、rollback、service mode、uninstall、WSL 和 source-development setup，請看 [文件](#文件)。

## 功能概覽

- **圖片優先瀏覽：** 用 Cards view 或 Explore view 快速掃案例。
- **搜尋和篩選：** 搜尋 title、prompt、tag、collection、source 和 note，也可以配合 collection filter 使用。
- **保存來源脈絡：** 原始 prompt、來源資料、翻譯或轉換後的 variant 可以放在同一張卡片。
- **管理私人 library：** 新增 / 編輯自己的 prompt card、結果圖、reference image、tag、note、source URL 和 collection。
- **一鍵複製 prompt：** 打開 item，選擇語言或來源 variant，直接複製。
- **本地生成：** 本地安裝版可選擇連接 ChatGPT / Codex OAuth。只要你的 ChatGPT account/subscription 有圖片生成權限，就可以由新 prompt 或已保存 reference 生成圖片，review 後 attach 到現有 item 或另存新 item。
- **保持 local-first：** database 和圖片檔案都留在本地 library directory。

## 搜尋 library

App 頂部的 search box 可以收窄目前看到的 references。現時版本是普通 keyword search，會搜尋 title、prompt、tag、collection name、source metadata 和 note。

例子：

```text
apple
poster design
product photo
awesome-gpt-image-2
電商
```

搜尋可以配合 collection filter：先在 **Filters** 選 collection，再輸入 keyword，就可以只在該 collection 裡面找。

## 本地生成

本地安裝版可以選擇連接 ChatGPT / Codex OAuth，不需要在 app 裡放 OpenAI API key。你需要一個有圖片生成權限的 ChatGPT account/subscription。

基本流程：

1. 啟動本地 app，打開 **Config**。
2. 連接 **ChatGPT / Codex OAuth**，在瀏覽器完成 device-login approval。
3. 回到 Image Prompt Library，由新 prompt 或已保存 reference 開始生成。
4. 在本地 inbox review 生成結果。
5. 把結果 attach 到目前 item，或另存成可再編輯 metadata 的新 item。

<p align="center">
  <img src="docs/assets/screenshots/generation-provider-connected.png" alt="Config drawer showing ChatGPT / Codex OAuth connected for local image generation" width="360" />
</p>

公開 GitHub Pages demo 不會做 live generation，也不會開放新增 / 編輯等 mutation controls。

目前生成行為、限制和 benchmark notes，請看 [`docs/GENERATION.md`](docs/GENERATION.md)。

## Sample data 與 attribution

第一次 setup 時，可以匯入可選 sample bundles，先有一批真實 prompt/image references 可以瀏覽和試用。這些 samples 來自開放的上游 project，匯入時會保留來源連結、致謝和 license notes。它們不是 Image Prompt Library 原創 artwork 或 prompt；原本的 creator 和 license 仍然會清楚保留。

| Sample source | License | Notes |
| --- | --- | --- |
| [`wuyoscar/gpt_image_2_skill`](https://github.com/wuyoscar/gpt_image_2_skill) | CC BY 4.0 | 第一個公開 sample package，也是預設 starter sample library。 |
| [`freestylefly/awesome-gpt-image-2`](https://github.com/freestylefly/awesome-gpt-image-2) | MIT | 較大的中文 prompt/image gallery，用於目前公開 demo 和可選 sample pack。 |

感謝兩個上游 project 開放這些 gallery。Image Prompt Library 做的是本地 app、匯入流程、瀏覽和管理介面；sample prompt 和圖片仍然保留各自的 source link、attribution 和 license terms。App code 則另外以 AGPL-3.0-or-later 授權。

Sample package details 和 checksums 請看 [`sample-data/README.md`](sample-data/README.md)。

## 文件

- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — install、update、rollback、service mode、uninstall、platform notes。
- [`docs/GENERATION.md`](docs/GENERATION.md) — ChatGPT / Codex OAuth generation workflow、result review、目前限制、benchmark link。
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — source setup、dev mode、configuration、data layout、backup。
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — 常見 runtime 和 setup 問題。
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — contributor setup、tests 和 project structure。
- [`ROADMAP.md`](ROADMAP.md) — planned work 和 project direction。

## License、privacy 與 allowed use

Image Prompt Library 的核心 application code 以 **AGPL-3.0-or-later** 開源。Copyright (C) 2026 Edward Tsoi。詳情請看 [`NOTICE`](NOTICE) 和 [`LICENSE`](LICENSE)。

如果組織想在 AGPL 以外的條款下使用、修改或 host Image Prompt Library，可以聯絡 maintainer 洽談 commercial license。

Privacy model：

- App 是 local-first，資料儲存在你的 device 上。
- 沒有 hosted user account，也沒有內建 cloud sync。
- 預設綁定 `127.0.0.1`，只在本機使用；除非你清楚理解 LAN exposure，否則不建議改 host。

## Project status

這是 public beta。Core browsing、search、本地 add/edit、可選本地 generation、versioned install、update/rollback，以及唯讀 online demo 現時已可使用。後續工作包括 service/update hardening、management-mode cleanup tools、search/sort polish、batch image editing、import-flow polish，以及更深入的 mobile Explore gestures。
