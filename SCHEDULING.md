# External scheduler — step by step

GitHub's clock keeps dropping Surgeon's schedules. This replaces the clock
and nothing else: the workflows stay exactly as they are, doing exactly what
they do. The only change is who presses "Run workflow" — a free website
instead of GitHub's own scheduler.

If the external service ever fails, GitHub's schedules are still in the
files as a fallback. Nothing is removed.

Everything below works from a phone. Budget about twenty minutes.

---

## Step 1 — upload the workflow files

Upload the five `.yml` files to `.github/workflows/`. They are identical to
what is already there apart from one addition: each now also answers to a
`repository_dispatch` event, which is the door the external scheduler knocks
on.

Nothing else changed. The existing schedules stay in place.

---

## Step 2 — make a token

This is the key that lets the scheduler start your workflows.

1. GitHub → tap your avatar (top right) → **Settings**
2. Scroll to the very bottom → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens**
4. **Generate new token**

Fill in:

- **Token name**: `surgeon-scheduler`
- **Expiration**: 1 year
- **Repository access**: *Only select repositories* → choose `Surgeon---Main`
- **Permissions** → **Repository permissions** → find **Contents** → set to
  **Read and write**

Then **Generate token**.

**Copy it immediately** — GitHub shows it once and never again. Paste it
somewhere safe; you will need it five times.

It looks like `github_pat_11ABC...`

> Contents write is what triggering a workflow requires. There is no
> narrower permission for it — that is GitHub's design, not a shortcut.

---

## Step 3 — prove the token works

Before setting up five scheduled jobs, confirm one manual request works.

Go to **reqbin.com**. No account needed.

- **URL**: `https://api.github.com/repos/AABEN777/Surgeon---Main/dispatches`
- Change **GET** to **POST**
- **Content** tab → choose **JSON** → paste:

```
{"event_type": "run-scan"}
```

- **Headers** tab → add two:

```
Authorization: Bearer YOUR_TOKEN_HERE
Accept: application/vnd.github+json
```

Tap **Send**.

**You want `204 No Content`.** Open your Actions tab — a Scan run should be
starting.

If instead you get:

- **404** — the token cannot see the repo. Check repository access and that
  Contents is *Read and write*.
- **401** — the token is wrong or was copied incompletely.
- **422** — the JSON body is malformed. Check the quotes are straight ones.

Do not continue until you see 204.

---

## Step 4 — set up the scheduler

Go to **cron-job.org** and create a free account. No card required.

For each job: tap **Create cronjob** and fill in.

**Common to every job**

- **URL**: `https://api.github.com/repos/AABEN777/Surgeon---Main/dispatches`
- Expand **Advanced**:
  - **Request method**: `POST`
  - **Headers** — add both:
    ```
    Authorization: Bearer YOUR_TOKEN_HERE
    Accept: application/vnd.github+json
    ```
  - **Request body**: as listed below

**The five jobs**

| Title | Schedule | Request body |
|---|---|---|
| Surgeon Scan | every 15 min, at :07 :22 :37 :52 | `{"event_type": "run-scan"}` |
| Surgeon Watch | every 5 min | `{"event_type": "run-watch"}` |
| Surgeon Analyze | every 15 min, at :04 :19 :34 :49 | `{"event_type": "run-analyze"}` |
| Surgeon Brief | daily 07:05 | `{"event_type": "run-brief"}` |
| Surgeon Derive | daily 04:40 | `{"event_type": "run-derive"}` |

Set the account timezone to **UTC** so these match what the workflows expect.

**Start with Surgeon Watch only.** Save it, wait five minutes, check the
Actions tab. If a Watch run appears on its own, the setup works and you can
add the other four with confidence.

---

## Step 5 — confirm it is working

After an hour, filter the Actions tab by:

```
event:repository_dispatch
```

Runs should be arriving steadily. Compare with `event:schedule`, which is
the one that has been failing.

cron-job.org also keeps an execution history per job showing the response
code. A column of green 204s means every trigger landed.

---

## If something goes wrong

**Nothing appears in Actions** — check the cron-job.org history. 204s mean
GitHub received the trigger and the problem is elsewhere; 401 or 404 means
the token or headers are wrong.

**Runs start but fail** — that is Surgeon failing, not the scheduler. Open
the run and read the log as usual.

**Double runs** — GitHub's schedule fired as well as the external one.
Harmless: the scan dedupes by contract address and the watcher is
idempotent. Once the external scheduler has proved itself over a few days,
the `schedule:` blocks can be deleted from the workflow files.

---

## What this does not fix

If GitHub Actions itself is down, the run fails whatever triggered it. This
fixes dropped *schedules* — the failure you have been hitting — not GitHub
being offline.
