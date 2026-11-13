# Research Computing correspondence: what was asked and what was answered in writing

Miami's Research Computing runs Redhawk and Talon. This file keeps their written answers about Talon in one place, with dates, so the project can point to them. A written answer is stronger evidence than the verbal answers from the 2026-11-06 meeting (`docs/clusters/talon_setup.md`, evidence labels). The answers are quoted exactly as received.

## 2026-11-12: four questions about limits and cost

**Sent by Jaxson Bugg to Dr. Donghyung Lee and Dr. Jens Mueller, 2:26 PM.** In plain terms, the email said that short tests on Talon suggest that generating 200,000 training examples could need up to about 51 GPU-days on a single GPU, and that the work can run as many restartable jobs of up to 3 days each (the limit mentioned in the call of 2026-11-06). It then asked:
1. Is there a limit on the GPU hours or days we may use?
2. Is there a limit on the number of GPUs we can use at one time?
3. Is there any rule that might lower our priority after heavy use, cut a job short when others need the nodes, or restrict access after some heavy jobs?
4. Please confirm in writing that Talon is free to use.

**Answered by Dr. Mueller, 4:37 PM, the same day:**

> 1. The only limit is the time per job. As we allow more users onto the system, competition for time slots will get bigger and wait times for the jobs to start will increase, hereby enforcing the fair-share policy built into the Slurm scheduler
>
> 2. You can use all 4 GPUs on a node if you can effectively use them. I believe the best way would be to allocate one GPU per job via the `--gres=gpu:1` Slurm directive. If your program is otherwise able to use multiple GPUs at once that's fine as well.
>
> 3. Run time will never be cut short but wait times for subsequent jobs may get longer.
>
> 4. Yes, it's free.

## What this means for the project (our reading, not a quote)

| Question | Written answer, in short | Consequence |
|---|---|---|
| GPU-hour limit | None; the only limit is the time per job (3 days) | The 200,000-example plan is not blocked by an allowance. The practical limit is how fast jobs start. |
| GPUs at once | All 4 GPUs of a node; one GPU per job (`--gres=gpu:1`) is recommended | Our layout (1 GPU per job, `--gres=gpu:nvidia_h100_nvl:1`) is what Research Computing recommends. Up to 4 single-GPU jobs can run side by side on one node, which would bring the roughly 51 GPU-days for 200,000 examples down to about 13 days of clock time (about 3 days for the 50,000-example fallback). |
| Priority and interruption | A running job is never cut short; later jobs may wait longer, under Slurm's fair-share policy | The work is submitted in restartable chunks. Start-up waits may grow after heavy use and as more users join, so a quiet cluster (as on 2026-11-12) is not a guarantee for later. |
| Cost | Free, in writing | The cost log stays for paid or metered calls only (since 2026-11-12, the Codex grader). |

## What is still not answered

- **Several nodes at once.** The answer says "all 4 GPUs on a node". It does not say whether GPUs on more than one node may be used at the same time. The 8- and 16-GPU lines of the throughput report assume that they may.
- **Storage beyond 500 GB**, the purge policy of any scratch space, and the **account's lifetime and renewal** (the project spans two semesters). These were not asked in this email.
- **Usage and data policies** in writing. The 2026-11-06 meeting said nothing changes without written notice, but nothing is in writing.
