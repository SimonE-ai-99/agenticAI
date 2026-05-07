# Building Autonomous Agents & Tool-Using Systems – Day 3

Source: `Day 3.pptx` – 21 slides

---

## Slide 1

### Day 3 BUILDING AUTONOMOUS AGENTS & TOOL-USING SYSTEMS

- Agent capabilities: tool-use, retrieval augmentation, action loops - Safety, guardrails, and constraints, Using frameworks: LangChain Agents, AutoGen Studio, CrewAI worker-manager roles - Hands-on use cases: Research automation agents - Business workflow agents.
- List of Experiments:
- Lab 6: Build a tool-using agent (web-search, calculator, document summarizer)


## Slide 2

### Simple Tool Execution

_Diagram comparing an LLM without tools vs. with tools:_

- **Without tool:** "What time is it?" → LLM → "Sorry, I do not have access to the current time"
- **With tool:** "What time is it?" → LLM → `get_current_time()` → LLM → "It's 3:20pm"

```python
from datetime import datetime

def get_current_time():
    """Returns the current time as a string"""
    return datetime.now().strftime("%H:%M:%S")
```


## Slide 3

### Examples

_Table mapping prompts to tools and outputs:_

| Prompt | Tool | Output |
|---|---|---|
| Can you suggest a sushi restaurant in San Francisco, CA? | `web_search(query='sushi restaurants in San Francisco')` | "Amami is a sushi restaurant in San Francisco…" |
| Show me customers who bought white sunglasses | `query_database(table='sales', product='sunglasses', color='white')` | "28 customers bought white sunglasses. Here is the list…" |
| How much money will I have after 10 years if I deposit $500 at 5% interest? | `interest_calc(principal=500, interest_rate=5, years=10)` or `eval("500 * (1 + 0.05) ** 10")` | $814.45 |


## Slide 4

### Multiple Tools

_Diagram of an agent chaining multiple tool calls:_

"Make an appointment with Alice on Thursday" → LLM → **CHECK CALENDAR** → returns times (Thursday 2pm, 3pm, 4pm) → LLM → **MAKE APPOINTMENT** → output ("Meeting created successfully!") → LLM


## Slide 5

### Planning

_Diagram showing the agent reasoning loop:_

**PLAN → THOUGHT → ACTION → OBSERVATION → ANSWER**

The loop cycles between THOUGHT, ACTION and OBSERVATION until the agent produces a final ANSWER.


## Slide 6

### Planning Loop

1. Give the agent access to tools
2. Prompt it to create a plan: "List the step-by-step actions to answer this question"
3. Execute the plan step-by-step
4. Repeat until you're done


## Slide 7

### Retail Example

_User prompt: "Any round sunglasses in stock under $100?"_

- **Step 1:** Use `get_item_descriptions` to find round frames
- **Step 2:** Run `check_inventory` on that list
- **Step 3:** Call `get_item_price` on the in-stock items and filter to under $100
- **Step 4:** Compose the answer


## Slide 8

### Plan as JSON

```json
{
  "plan": [
    {
      "step": 1,
      "description": "Find round sunglasses",
      "tool": "get_item_descriptions",
      "args": {"query": "round sunglasses"}
    },
    {
      "step": 2,
      "description": "Check available stock",
      "tool": "check_inventory",
      "args": {"items": "results from step 1"}
    }
  ]
}
```


## Slide 9

### Plan as Code

```python
# Load transaction data
df = load_csv('transactions.csv')
# Parse dates
df['date'] = parse_dates(df['date'])
# Sort by date
df = df.sort_values('date')
# Take last 5
recent = df.tail(5)
# Return amounts
return recent['amount'].tolist()
```


## Slide 10

### Safety, guardrails, and constraints – Guardrails as Code

_Diagram showing a deterministic code-based guardrail layer:_

The agent runs through THOUGHT → ACTION → OBSERVATION → ANSWER ("My final answer is…") and the answer is passed to a **GUARDRAILS** layer. A code check (e.g. `if len < 200: True`) decides:
- ✗ Failed → loop back to THOUGHT
- ✓ Passed → return answer to user


## Slide 11

### Safety, guardrails, and constraints – Guardrails as LLM

_Same guardrail pattern, but with an LLM as the validator:_

The agent's answer is sent to an **LLM JUDGE** that asks "Is this answer reasonable given…". The judge feeds back into the GUARDRAILS layer:
- ✗ Failed → loop back to THOUGHT
- ✓ Passed → return answer to user


## Slide 12

### Reflection

- **Version 1 (first draft):** "Hey, let's meet next month to discuss the project. Thanks"
- **Reflection step:** _The model reads v1 and spots these issues — unclear timeline, missing sign-off, tone feels rushed._
- **Version 2 (revised):** "Hi Alex, let's meet between January 5–7 to discuss the project timeline. Let me know what works for you. Best, Marina"


## Slide 13

### Reflection w/ Feedback

_Diagram of a code-generation reflection loop:_

"Write code for task x" → LLM → code v1 → execute code → ✗ (error) → LLM (reads code output, errors) → working code!


## Slide 14

### Using frameworks - LangChain Agents.


## Slide 15

### Problems without langchain

_Three-panel illustration of pre-LangChain LLM limitations:_

- **Panel 1:** "What's the weather today in Bangalore?" → The model incorrectly says something. **Why?** It wasn't connected with Weather API tools earlier from ChatGPT.
- **Panel 2:** "Summarize this book into 5 lines." → There is no option to **UPLOAD PDFs**. **Why?** It can't extract the information present inside the PDFs.
- **Panel 3:** "Who was the first person to land on the moon?" → LLM → Neil Armstrong (works). "What is the refund policy on t-shirt?" → LLM → I don't know (fails — no access to internal data).


## Slide 16

- LangChain is an open-source framework designed to help developers build applications powered by large language models (LLMs) like OpenAI GPT.
- Instead of just sending a single prompt to an AI model and getting a response, LangChain lets you create more complex, structured workflows around LLMs.


## Slide 17

### LangChain Ecosystem

- LangChain: Provides base abstractions and integrations (models, vector stores, loaders) to connect LLMs with external data.
- LangGraph: An extension designed for building complex, agentic workflows and multi-agent systems, allowing LLMs to loop and call tools iteratively.
- LangSmith: A developer platform for debugging, evaluating, and monitoring LLM applications throughout their lifecycle.
- LangServe: Facilitates the deployment of LangChain chains and agents as REST APIs.


## Slide 18

### What can LangChain do?

- Chain multiple steps together
- Example: Take user input → process it → query a database → generate an answer.
- Connect to external data
- PDFs, documents, websites, APIs, databases.
- Build chatbots with memory
- The bot remembers previous conversations.
- Use tools and agents
- AI can decide what action to take, like searching the web or running code.

**Key Components**

- LLMs – the core AI models
- Chains – sequences of operations
- Agents – decision-makers that choose actions
- Memory – stores past interactions
- Retrievers – fetch relevant data (for RAG apps)


## Slide 19

### Lab Activity: Designing an agent capable of multi-step planning.

- Goto https://crewai.com/
- Register for sign in
- Try with the below prompt
- I want to build a weekly learning assistant. It should ask for a topic to learn about, then research the topic, find the best resources and generate a personalized study plan.


## Slide 20

### Lab Demo in Colab

- Build a tool-using agent for web-search
- Build a tool-using agent for calculator.


## Slide 21

### Use cases

- Research automation agents.
- Business workflow agents.
- Build a sustainability-support agent (energy data assistant)
