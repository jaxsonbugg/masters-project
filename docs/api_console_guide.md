# Using the Claude API and the Claude Console: a beginner's guide for this project

Written 2026-10-06. This guide explains, in plain language, how to set up and watch the Claude API through the Claude Console website, and how that connects to the scripts in this project. It was written from Anthropic's documentation pages (read on 2026-10-06), not from clicking through your account. **Button names and menu positions can change, so if something looks different, trust the screen and tell me, and I will fix this page.**

## 1. The big picture

The **Claude API** is how a program (like our `generate_benchmark.py`) asks Claude a question and gets an answer back, paid per use. The **Claude Console** is the website where you manage the account behind it: the money, the keys, the limits and the usage reports. They are two sides of one thing:

- The **script** does the work and sends requests, using a secret **API key**.
- The **Console** is where you decide how much the script is allowed to spend, and where you check afterwards what it actually spent.

An analogy: the key is a prepaid card the script carries, the Console is the bank's website where you load money onto the card, set a daily limit, and read the statement.

Everything below is at [platform.claude.com](https://platform.claude.com). (This is separate from claude.ai, the chat website, and separate from your Claude Code subscription.)

## 2. Vocabulary you will see

- **Token:** the unit the API counts and charges for, a short chunk of text (about three quarters of an English word). You pay separately for tokens you send (**input**) and tokens Claude writes (**output**).
- **Thinking tokens:** before answering, Sonnet 5.5 can "think" in hidden text. You are billed for it at the output price, the expensive one. The **effort** setting (low, medium, high) steers how much it thinks.
- **Batch API:** a cheaper way (half price) to send many requests at once and collect the answers later, within 24 hours (usually under an hour). The normal way, answers right now, is called **standard**.
- **Organization:** your account. It holds the credit balance and billing.
- **Workspace:** a labeled box inside the organization for one project, with its own API keys and (importantly) its own spend limit. Every organization has a **Default Workspace** that cannot be limited, renamed or deleted.
- **Tier:** a level your organization sits on, which sets the maximum requests and tokens per minute and a monthly spending cap. New accounts can start on a low tier and move up automatically as they use the API.
- **Credits:** prepaid money. Usage subtracts from it.

## 3. One-time setup (do this before the big benchmark run)

These steps use the Console menus named in the documentation.

1. **Create a workspace for this project.** Go to **Settings > Workspaces**, click **Create workspace**, name it `masters-project`, choose a color, click **Create**. A selector in the top-left corner switches between workspaces. *Why:* the Default Workspace cannot have limits, and a dedicated workspace lets you cap just this project and see its usage and batches separately. (Only an organization admin can create workspaces; as the owner of your own account you are one.)
2. **Create the API key inside that workspace.** Open the workspace, go to its **API keys** tab (or Settings > API keys and choose the workspace), click **Create key**, name it something like `masters-pilot`, and copy it immediately, because Anthropic shows it only once. Put it in your Windows user environment variable `ANTHROPIC_API_KEY` as described earlier; never in a file, a chat or a document. A key created in a workspace works only there, so its usage and batches land in that workspace.
3. **Check your credits.** Go to **Settings > Billing**. You should see the balance (yours was $30 when we started). Keep auto-reload off at first, so you cannot spend more than you loaded.
4. **Set an organization spend limit.** On the **Billing** page, find **Spend limits** and click **Adjust limit** (or **Set limit**). Enter a monthly limit you are comfortable with, for example $50. If a limit you set is reached, requests are refused with an error (HTTP 400, "You have reached your specified API usage limits") until you raise it or the month rolls over.
5. **Set a workspace spend limit.** In **Settings > Workspaces**, open `masters-project` and go to its **Spend limits** tab. Set a monthly cap for the project (the pilot needs well under $75; for example $40 now, raised later), and optionally an alert at a lower amount. This is the strongest guard against a mistake, because it is enforced by Anthropic, not by our script.
6. **Look at your rate limits.** Go to **Settings > Limits** (the Rate limits page). It shows your tier and the requests and tokens per minute allowed for each model. For Sonnet 5.5 the documented Start-tier limits are 1,000 requests per minute and 400,000 output tokens per minute, far more than we need; new accounts may start lower ("Evaluation" tier), and limits rise as you use the API.

## 4. Running the 20-question trial (what happens, step by step)

The trial is run from a terminal, not the website; the website is where you check the results afterwards.

1. **`plan`** prints the 20 "slots" (what category, subtopic, difficulty and answer type each question must have). It makes no API call and costs nothing.
2. **`trial --dry-run`** shows the cost picture and exactly the request that would be sent, without sending it. It prints, before any money is spent: the worst case for one call, the worst case for all 20 calls, a typical expectation, and your cap. (Worked example from this project: each call is limited to 5,000 output tokens, so the worst case per call is about 1,163 input tokens x $2 per million + 5,000 output tokens x $10 per million = about $0.0525; times 20 calls is about $1.05, which is under the $3.00 cap.)
3. **`trial`** makes the 20 real calls one after another, reading your key from the environment. After each call it adds up the real cost from the token counts the API returns, and it stops itself if spending plus the worst case of the next call would pass the cap.
4. **Outputs** are saved in a dated folder under `C:\masters_project_large\data\teacher_outputs\` (raw responses and a log) and a small review copy in `results/benchmark_trial/` in the repository. The log records the model, effort, prompt version and hash, token counts, dollars and the workspace the key belongs to.

**What actually happened on the first run (2026-10-07):** the dry run said the worst case for all 20 calls was $1.05 and a typical run about $0.35. The real run used 28,850 input tokens and 7,017 output tokens and cost **$0.1279**, so the cap of $3.00 was never close. Each response also carries a header naming the workspace the key belongs to, and the script logged it (`wrkspc_01SnSe...` in this run). The header looks the same whether it is the Default Workspace or one you created, so to learn which one your key is in, open Settings > Workspaces in the Console and compare the id; if it is the Default Workspace, set up the dedicated workspace in section 3 before the big run.

**What the trial tells us:** whether the key and prompt work, how many tokens a question really takes (so what 1,000 will cost), how many questions came back malformed or with an answer that is too long, and what the questions look like, so you can judge them yourself before we spend more.

## 5. Checking the result in the Console

Open **Usage** ([platform.claude.com/usage](https://platform.claude.com/usage)). It shows token and request charts by model and workspace, and the rate-limit charts. Usage can take a little while to appear, so if the numbers look low, wait a few minutes. Compare the total with the cost our script printed and with the row we add to `docs/cost_log.md`. They should agree to within a cent or so; if the Console shows noticeably more, something else is using the key.

Also look at the balance on **Billing**: it should have dropped by about the same amount.

## 6. Batches in the Console (for the 1,000-question run)

For the big run we use the Batch API. Each batch appears on the Console **Batches** page for the workspace it was created in (the documentation gives the address pattern `platform.claude.com/settings/workspaces/<workspace>/batches`). What you will see:

- **Status:** `in_progress` while Claude works, `ended` when every request has finished (most batches finish within an hour; the maximum is 24 hours, and requests that do not finish in time expire and are not billed).
- **Counts:** how many requests succeeded, errored, expired or were canceled.
- **Cancel:** you can cancel an in-progress batch; delete one after processing.
- **Results:** kept for 29 days after the batch is created, so download them the same day they finish. Our `fetch` command downloads them to a dated folder and records the cost. (Downloading from the Console may be switched off by organization settings; the script path works regardless.)

Why batches are good for overnight runs: after you submit, the work happens on Anthropic's computers. Your PC can be off. In the morning you run `fetch` once and get everything.

## 7. Common messages and what they mean

- **HTTP 401 (authentication error):** the key is missing, mistyped or deleted. Check the environment variable (open a new terminal after setting it).
- **HTTP 400 mentioning "specified API usage limits":** you hit a spend limit you set (organization or workspace). Raise it or wait for the next month.
- **HTTP 400 "invalid request":** something in the request is not accepted (for example a setting the model does not allow). The script stops and prints the message instead of retrying.
- **HTTP 429 (rate limit):** too many requests or tokens per minute. The script's library retries automatically a couple of times; if it keeps happening, slow down. A 429 with the words "monthly API usage threshold" is the tier's spending cap and does not clear until the month changes.
- **Truncated answer ("max_tokens"):** the model ran out of its output allowance, often because it thought a lot. The script flags these; the fix is a bigger `max_tokens` or a lower effort.

## 8. Good habits

- Run the dry run first, and always read the cost lines before the real run.
- One key per purpose and phase (`masters-pilot` now, a new one for the big run), and delete keys you no longer need.
- Never paste the key anywhere. If you do by accident, delete it in the Console and create a new one.
- After every paid run, add a row to `docs/cost_log.md` (the project rule) and compare it with the Console's Usage page.
- Prices change. The numbers in our documents come from Anthropic's pricing pages as of 2026-10-06 ($2 input and $10 output per million tokens for Sonnet 5.5, half for Batch).

## 9. Sources (read 2026-10-06)

[Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces), [Rate limits and spend limits](https://platform.claude.com/docs/en/api/rate-limits), [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing), [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview).
