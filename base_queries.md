### 1. Query hello. The minimum DAG

```
Say hello.
```
Two nodes. The Planner emits a Formatter as the only successor. The Formatter answers. Wall-clock under three seconds. The Planner's prompt allows this shape because the query needs neither research nor structure; the Formatter is the appropriate terminal. Students who run this first see the smallest possible DAG that the architecture can produce.

### 2. Query A. Shannon Wikipedia (S7 carryover)

```
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth
date, death date, and three key contributions to information theory.
```

Four nodes. Planner emits researcher then distiller then formatter. The Researcher's tool-use loop runs fetch_url once and produces the page content. The Distiller extracts the three structured fields; a Critic auto-inserted between the Distiller and the Formatter returns pass on this content (the dates and contributions are clearly present in the page). The Formatter produces the final answer.

The trace under Session 8 is structurally the same as under Session 7. The wall-clock improvement is marginal because the query is sequential in its dependency structure. The architectural benefit is the trace itself: four named nodes, each with one job, instead of eight iterations of a single loop maintaining its goal list across turns.

### 3. Query I. Three city populations (the parallel-fan-out case)

```
find the populations of London, Paris, and Berlin and tell me which two are closest in size
```
Seven nodes. Planner emits three Researchers concurrently, then a Coder, then a Formatter alongside a SandboxExecutor. Wall-clock sixty-two seconds against one hundred twenty-five for Session 7. Token bill seventeen thousand input against fifty-four thousand for Session 7.

### 4. Query J. Graceful failure

```
Read /nonexistent/path.txt and tell me what's in it.
```

Two nodes. The Planner reads the query, recognises that no part of the agent can plausibly satisfy a request for a file that does not exist, and emits a Formatter directly with a failure note in its inputs. The Formatter produces an answer that explains the path could not be accessed. No tool is dispatched.

The query exercises a path the orchestrator must handle gracefully: the Planner's first pass produces a degenerate DAG (planner to formatter, no work in between) because the query is unanswerable. The brief on this query allowed two outcomes: the agent fails-fast by planning, or the agent attempts the file read and fails-loud at Action. The Planner chose the first. Both are defensible; the first is faster and saves the Action call.

### 5. Query K. Resumable execution

```
For Lagos, Cairo, and Kinshasa, find current populations and growth rates
and tell me which is growing fastest.
```

The first process runs the query and is killed by SIGKILL at iteration four of the parallel Researcher layer. The graph file on disk contains the Planner as complete, two Researchers as complete, and one Researcher as running. The Executor was mid-gather at the moment of kill.

```
flow.py --resume s8_K_resumed_v2
```

The resume reads the graph from disk. The running Researcher is reset to pending. The Executor re-runs the pending Researcher, which re-executes its tool-use loop from the top. The Coder, Formatter, and SandboxExecutor then run. Wall-clock across the two processes is roughly seventy seconds against an estimated ninety seconds for a fresh single-process run; the resume's overhead is the re-execution of the killed Researcher's tool calls. The final answer correctly names Lagos as the fastest-growing city at approximately three point seventy-eight percent.