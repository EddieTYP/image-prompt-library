# Local Generation Guide

Local installs can generate images through **ChatGPT / Codex OAuth** or an optional **xAI Grok Imagine** API key. The GitHub Pages Online Read Only Demo stays read-only and does not expose generation or mutation controls.

## What the local generation flow does

Once connected, you can:

- Generate a new image from a fresh prompt.
- Queue a `Generation set` of 3, 5, or 10 independent variations from the same prompt and settings.
- Generate a variant from an existing reference.
- Review generated results before saving them into the library.
- Attach a result to its unchanged source item when available.
- Save a result as a new item with editable metadata.
- Keep useful generation details such as provider, model, original item, and batch position.
- Use prompt variables such as `{{subject}}`, `{{style}}`, or `{{主體}}` in reusable template prompts and fill them before each generation.

No OpenAI API key is required for the ChatGPT / Codex OAuth path. xAI is separate and usage-billed. You can add its API key directly under **Config → Providers**, or manage it with the `XAI_API_KEY` environment variable.

## Privacy boundary

Generation is local-install only. The public GitHub Pages demo does not perform live imports or generation and does not expose Add/Edit/private-library controls.

The app-owned OAuth store and local provider config must resolve outside the active library. If `IMAGE_PROMPT_LIBRARY_AUTH_PATH` or `IMAGE_PROMPT_LIBRARY_CONFIG_PATH` resolves to the library itself or any child path, startup stops before the database or credential files are read. Library-managed media roots (`originals`, `thumbs`, `previews`, `generation-results`, and `generation-references`) must also resolve inside the library; external symlink or junction targets are rejected so they cannot alias app-owned state. The app does not move or delete an unsafe file automatically.

For an existing unsafe override, move the file manually to `~/.image-prompt-library/auth.json` or `~/.image-prompt-library/config.json`, update or unset the override, then restart. Treat any older backup that may contain the file as sensitive; reconnect the provider if the credential may have been exposed. OAuth tokens and xAI API keys must never be committed to git, sample bundles, backups, or GitHub Pages exports.

## Set up a provider

Open **Config → Providers**, then choose **Connect** under **ChatGPT / Codex OAuth**. Follow the authorization link, enter the one-time code, approve the request, then return to Image Prompt Library and choose **Check authorization**.

The browser may label the request **Codex CLI**. Only approve a flow you started from your local Image Prompt Library app. When setup is complete, the provider shows **Connected**.

To use xAI, paste its API key into **xAI Grok Imagine** and choose **Save key**. The app writes it to its local credential file outside the Library, never returns the key to the browser after saving, and never writes it into the Library database, generation metadata, backups, samples, or the public demo. You can replace or remove the saved key from the same screen.

Advanced setups can provide `XAI_API_KEY` through the local process environment instead. An environment key takes precedence over the saved key; while it is active, Config shows that the credential is environment-managed and does not offer replace or remove controls.

xAI generation sends the prompt and any reference images to xAI. Its current API policy retains requests and responses for 30 days by default; eligible teams can opt into Zero Data Retention. Check the current [xAI security policy](https://docs.x.ai/console/faq/security) before using sensitive material.

## Generate and review results

Open **Create image**, choose the provider, enter a prompt, and select the available settings. **Generate** creates one result; the adjacent menu creates 3, 5, or 10. Each result uses a separate generation request. Template prompts can include `{{variables}}`; the composer previews the resolved prompt before sending.

The model menu offers three GPT-5.6 choices. **Recommended · gpt-5.6-terra** is the balanced default, `gpt-5.6-sol` is the highest-capability option, and `gpt-5.6-luna` is the lighter option for simpler or higher-volume work. Existing custom model overrides remain available after these built-in choices.

For xAI, the app uses `grok-imagine-image-2.0` at 1K resolution. Low and Medium quality are available, and image edits can use up to three ordered reference images. Results are requested as base64 media and saved locally instead of depending on temporary hosted URLs. Current xAI pricing is US$0.04 per 1K Low image, US$0.06 per 1K Medium image, plus US$0.01 for each reference image; confirm the current [model pricing](https://docs.x.ai/developers/models/grok-imagine-image-2.0) before a large batch.

Review completed results from the **Work queue**. For each result, choose **Save as new item**, **Use result as edit input**, **Retry**, or **Discard**. **Attach to current item** is also available when the result came from an unchanged saved reference. **Use as draft** copies the result's prompt and reusable settings back into the composer. Batch review keeps each result's position and advances to the next unfinished result. Using a result as a draft or edit input pauses review; **Continue review** returns to the remaining results.

Queued and running jobs remain in the Work queue if you close or refresh the page. Deleting a source reference does not cancel them; completed detached results can still be saved as new items.

<p align="center">
  <img src="assets/screenshots/generation-review-result.jpg" alt="Generation review showing the first result in a three-result batch" width="100%" />
</p>
<p align="center"><sub>Review each result before you save, reuse, retry, or discard it.</sub></p>

Before saving a result as a new reference, edit its details. The read-only generation record shows the provider, model, batch position, and original item when available. Internal identifiers are not displayed.

<p align="center">
  <img src="assets/screenshots/generation-save-as-new-item.jpg" alt="Save as new reference with editable details for result 1 of 3" width="100%" />
</p>
<p align="center"><sub>Edit the details before saving the result to your library.</sub></p>

## When generation fails

The app gives a short next step for each failure:

- If the prompt is blocked, edit it and generate again.
- If the provider rate-limits requests, the failed result stays available for manual retry while untouched queued jobs wait.
- If the provider is unavailable, retry shortly; the prompt and references stay with the job.
- If authorization is required, open **Config → Providers**, reconnect, then retry.
- For other failures, retry the result or edit the prompt first.

The composer can show the sanitized provider error under **Provider details** as secondary diagnostic text. The queue intentionally shows only the classified guidance. Neither surface displays credentials or unsanitized provider responses.

## Current provider notes

The local queue has no artificial submission cap and runs up to five generation jobs at once. Additional jobs wait in the Work queue.

If a provider reports a rate limit, the app pauses only that provider's queue before continuing untouched queued jobs. The failed result stays failed until you retry it. Normal OAuth renewal happens in the background; reconnect only when the app says authorization is required. For xAI authentication errors, replace the saved key under **Config → Providers**. If the key is environment-managed, correct `XAI_API_KEY` and restart the app.

## Benchmark note

While building Image Prompt Library's Image 2.0 generation workflow, the project benchmarked GPT-5.5, GPT-5.4, and GPT-5.3-Codex across Low, Medium, and High quality. These are historical results, not the current model catalogue.

The current app receives its selectable orchestrator models and default from provider status. The built-in choices are `gpt-5.6-terra`, `gpt-5.6-sol`, and `gpt-5.6-luna`; `gpt-5.6-terra` is the recommended default. Users can still change the model and quality manually.

See the benchmark notes and images in [`generation-matrix-chatgpt-codex-impasto-florals-2026-05-01.md`](generation-matrix-chatgpt-codex-impasto-florals-2026-05-01.md).
