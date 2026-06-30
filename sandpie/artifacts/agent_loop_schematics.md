# AI Agent Loop Schematics — Research Summary

> Primary sources analyzed:
> - kshvakov.github.io "AI Agent Course — Ch 4: Autonomy and Loops"
> - mindstudio.ai "What Is the ReAct Loop?"
> - Anthropic research (widely cited canonical pattern)
> - Yao et al. 2022 "ReAct: Synergizing Reasoning and Acting in Language Models"

---

## The Core Pattern: ReAct

**ReAct** = **Re**ason + **Act**. The simplest canonical agent loop is exactly three stages per iteration:

```
┌───────────────┐
|  1. THOUGHT     |  ← Reason about the current situation
|     ("What do   |     "What do I know? What do I need?"
|      I need?")  |
└───────────────┘
         |
         ▼
┌───────────────┐
|  2. ACTION      |  ← Call a tool / function
|     (tool call) |     search(), read_file(), run_python(), etc.
└───────────────┘
         |
         ▼
┌───────────────┐
|  3. OBSERVATION |  ← Receive result
|     (tool result|     "95% disk usage", "Paris: 14°C, 70% rain"
|      / error)   |
└───────────────┘
         |
         └─────→ Loop back to THOUGHT
```

**"There is no magic here — it's simply a loop where the model processes the results of previous actions in context and generates the next step."** — kshvakov course

---

## The Full Loop (with planning layer)

For multi-step tasks, a planning layer is added before execution:

```
┌────────────────────────────────────────────────────────────┐
|  INPUT: User task + current state + available tools |
└────────────────────────────────────────────────────────────┘
                 |
                 ▼
┌────────────────────────────────────────────────────────────┐
|  PLANNER: "Given the goal and state, what is the   |
|           SINGLE most logical next concrete step?"  |
|                                                      |
|  Output: <PLAN> step, tool_hint, expected_outcome   |
└────────────────────────────────────────────────────────────┘
                 |
                 ▼
┌────────────────────────────────────────────────────────────┐
|  ACTOR: "Given the plan, emit EXACTLY ONE valid    |
|          JSON tool call matching the schema."       |
|                                                      |
|  Output: {"tool": "...", "arguments": {...}}        |
└────────────────────────────────────────────────────────────┘
                 |
                 ▼
        ┌───────────┐
        |   EXECUTE    |  ← Run the tool, get result/error
        └───────────┘
               |
               ▼
┌────────────────────────────────────────────────────────────┐
|  EVALUATOR: "Was this step successful? Is the      |
|              overall task done? What should the     |
|              next step be?"                         |
|                                                      |
|  Output: {"done": true|false, "state": {...},       |
|           "reasoning": "..."}                       |
└────────────────────────────────────────────────────────────┘
                 |
                 └───── if !done, loop with updated state
```

---

## Key Insight: Zero-Shot vs Streaming Agents

| Property | Streaming agent | Zero-shot (our approach) |
|----------|-----------------|--------------------------|
| Context grows? | Yes — every turn appends to `messages[]` | No — each stage starts fresh |
| Error compounding? | Yes — wrong reasoning poisons future turns | No — each stage is independent |
| Model size required | Large (needs to hold full history) | Small (short prompts only) |
| ReAct stages visible | Hidden in single LLM call | Explicit: planner → actor → evaluator |

**Why this works:** "Junior employee model. A loop iteration limit is 'time to escalation'. If a new hire spends 20 attempts on the same problem — they're expected to call the team lead. Same with an agent: hit the limit, hand control back to a human." — kshvakov course

---

## Minimal Pseudocode (the entire loop)

```
while not done and turns < MAX:
    # 1. Plan
    plan = llm("You are a planner. Task: ... State: ... Tools: ...")

    # 2. Act (emit tool call)
    call = llm("You are an actor. Plan: ... Tool schemas: ...")

    # 3. Observe (execute)
    result = execute_tool(call.tool, call.arguments)

    # 4. Evaluate
    eval = llm("You are an evaluator. Task: ... Result: ...")
    done = eval.done
    state = eval.state
```

---

## Why Tool Descriptions Must Be Available at EVERY Stage

The original error in `zeroshot.js`: planner only got a **name-only** list of tools (`- file: read_file, write_file, ...`). Without parameter schemas (what args does `run_python` take?), the planner cannot make informed decisions.

**Fix:** Pass the **full JSON schemas** (`${toolSchemas}`) to:
- `planner` — so it knows what each tool can do
- `compressor` — so it can distill the right schema
- `actor` — so it can construct valid JSON
- `evaluator` — so it knows whether the result makes sense given tool capabilities

This is the canonical approach in every framework (LangChain, OpenAI Assistants, Anthropic):
```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search the web via DuckDuckGo",
    "parameters": { "type": "object", "properties": {...} }
  }
}
```
