# Agent Architectures, Memory & Planning ? Day 2

Source: `Day 2.pptx` ? 49 slides

---

## Slide 1

### Day 2 AGENT ARCHITECTURES, MEMORY & PLANNING

- Cognitive architecture: perception, reasoning, memory, action - Memory systems in agents: short-term memory, episodic memory, vector-store memory, long-term memory - Planning systems: task decomposition, tree of thought, planner-executor architecture - Tool-calling & API integration - Evaluator-planner loops - Safety layers & guardrails.


## Slide 2

### Cognitive architecture

- Cognitive architecture represents a paradigm shift from passive Generative AI to autonomous systems that actively achieve multi-step goals.
- This architecture mimics human-like thinking by integrating four core modules—Perception, Reasoning, Memory, and Action—into a continuous loop of planning, acting, and adapting.


## Slide 3

- Cognitive architecture..


## Slide 4

- Perception Layer: Gathers and interprets data from the environment, using multi-modal inputs (text, voice, images, screen context) to provide situational awareness.
- Reasoning/Cognitive Module: The "brain" of the agent, usually powered by a Large Language Model (LLM), which performs task decomposition, planning, and decision-making.
- Memory Systems: Enables context retention and long-term learning, crucial for autonomous operation over extended periods.
- Short-term Memory: Context window (conversation history, current task state).
- Long-term Memory: Vector databases storing past experiences, documents, and knowledge.
- Action Module: Executes plans using tools such as APIs, code interpreters, and software applications to create tangible results.
- Cognitive architecture..


## Slide 5

### Memory systems in agents

- Short-term memory.
- Episodic memory.
- Vector-store memory.
- Long-term memory.


## Slide 6

### Short-term memory

- Short-term memory (STM) enables an AI agent to remember recent inputs for immediate decision-making. This type of memory is useful in conversational AI, where maintaining context across multiple exchanges is required.
- For example, a chatbot that remembers previous messages within a session can provide coherent responses instead of treating each user input in isolation, improving user experience. For example, OpenAI’s ChatGPT retains chat history within a single session, helping to ensure smoother and more context-aware conversations.
- STM is typically implemented using a rolling buffer or a context window, which holds a limited amount of recent data before being overwritten. While this approach improves continuity in short interactions, it does not retain information beyond the session, making it unsuitable for long-term personalization or learning.


## Slide 7

### Episodic memory

- Episodic memory allows AI agents to recall specific past experiences, similar to how humans remember individual events. This type of memory is useful for case-based reasoning, where an AI learns from past events to make better decisions in the future.Episodic memory is often implemented by logging key events, actions and their outcomes in a structured format that the agent can access when making decisions.For example, an AI-powered financial advisor might remember a user's past investment choices and use that history to provide better recommendations. This memory type is also essential in robotics and autonomous systems, where an agent must recall past actions to navigate efficiently.


## Slide 8

### Long-term memory

- Long-term memory (LTM) allows AI agents to store and recall information across different sessions, making them more personalized and intelligent over time.
- Unlike short-term memory, LTM is designed for permanent storage, often implemented using databases, knowledge graphs or vector embeddings. This type of memory is crucial for AI applications that require historical knowledge, such as personalized assistants and recommendation systems.
- For example, an AI-powered customer support agent can remember previous interactions with a user and tailor responses accordingly, improving the overall customer experience.
- One of the most effective techniques for implementing LTM is retrieval augmented generation (RAG), where the agent fetches relevant information from a stored knowledge base to enhance its responses.


## Slide 9

### Semantic memory

- Semantic memory is responsible for storing structured factual knowledge that an AI agent can retrieve and use for reasoning. Unlike episodic memory, which deals with specific events, semantic memory contains generalized information such as facts, definitions and rules.
- AI agents typically implement semantic memory using knowledge bases, symbolic AI or vector embeddings, allowing them to process and retrieve relevant information efficiently. This type of memory is used in real-world applications that require domain expertise, such as legal AI assistants, medical diagnostic tools and enterprise knowledge management systems.
- For example, an AI legal assistant can use its knowledge base to retrieve case precedents and provide accurate legal advice.


## Slide 10

_(no text content ? likely image/diagram only)_


## Slide 11

### Planning systems

- Planning systems in modern AI, particularly within LLM-based agentic workflows, are designed to enhance reliability, handle long-horizon tasks, and reduce cognitive load on the language model.
- They collectively move agents from reactive, single-step prompts to strategic, multi-step problem solving.
- Approaches:
- Task decomposition.
- Tree of thought.
- Planner-executor architecture.
- These approaches combined allow AI agents to manage complex tasks more reliably, reducing hallucinations and error propagation compared to traditional, monolithic prompting.


## Slide 12

### 1. Task Decomposition

- Task decomposition involves breaking down complex, high-level goals into smaller, manageable subtasks. This approach is crucial for long-horizon tasks, allowing agents to handle complex objectives by addressing them sequentially.
- Techniques: Approaches include hierarchical decomposition, where a high-level plan is generated first, and recursive decomposition, which breaks down tasks as needed if an executor fails.
- Benefits: This technique enables local correction of errors, reduces context window limitations by simplifying subtasks, and improves accuracy in complex environments.
- Examples: Systems like ROMA use hierarchical decomposition to create a directed acyclic graph (DAG) of subtasks, while Task-Decoupled Planning (TDP) uses a supervisor to decompose tasks for isolated, robust execution.


## Slide 13

_(no text content ? likely image/diagram only)_


## Slide 14

### 2. Tree of Thoughts (ToT)

- Tree of Thoughts (ToT) is a prompting technique that extends beyond linear "Chain of Thought" by allowing AI to explore multiple reasoning paths.
- Mechanism: It operates by generating "thoughts" (steps) at each stage of a problem, simulating a tree search structure.
- Process: The model acts as a search algorithm that explores different branches, evaluates the "value" of each state (using self-evaluation), and decides on the optimal path forward.
- Use Cases: ToT is particularly useful for tasks requiring non-linear planning, brainstorming, or deep, strategic reasoning that cannot be resolved in a single, straight-line thought process.


## Slide 15

### 3. Planner-Executor Architecture

- This architecture separates the reasoning, strategic planning process (Planner) from the action-oriented tool usage (Executor), creating a more reliable "plan-and-act" workflow.
- Planner: Responsible for generating high-level plans, decomposing tasks, and structuring the workflow.
- Executor: Takes the structured plan and executes specific actions or tool calls within the environment.
- Dynamic Re-planning: Advanced versions (e.g., Plan-and-Act, ReCAP) allow the agent to re-plan at each step if the executor fails to meet the subtask objectives, enhancing resilience to environment variations.
- Examples: ROMA, ReAct, and Task-Decoupled Planning (TDP) are examples of systems implementing these structures, often using LangGraph for orchestration.


## Slide 16

_(no text content ? likely image/diagram only)_


## Slide 17

_(no text content ? likely image/diagram only)_


## Slide 18

### Rule-Based Task Planner (Offline Agent)

- https://colab.research.google.com/drive/1qefOLMHe4Cog8wWZFQ3On5oCg49bxoi3#scrollTo=Y-ixfsg0Dl4Y


## Slide 19

### Real-Time Web Search Agent

- https://colab.research.google.com/drive/1PKet_7RfwPxolBZA7HYX0V0I9ZbuH-Zo#scrollTo=0T-WxSzcv-hr


## Slide 20

_(no text content ? likely image/diagram only)_


## Slide 21

_(no text content ? likely image/diagram only)_


## Slide 22

_(no text content ? likely image/diagram only)_


## Slide 23

_(no text content ? likely image/diagram only)_


## Slide 24

### https://colab.research.google.com/drive/1nlo3clRQIiiDY7MlEq30MNE7AuWbfbTJ

- https://colab.research.google.com/drive/1XrY4CxMomcZeMNsmdmt75g-px_CpO97b


## Slide 25

### Tool-calling & API integration

- Tool calling refers to the ability of AI models to interact with external tools, APIs or systems to enhance their functions.
- Instead of relying solely on pretrained knowledge, an AI system with tool-calling capabilities can query databases, fetch real-time information, execute functions or perform complex operations beyond its native capabilities.
- Tool calling, sometimes referred to as function calling, is a key enabler of agentic AI. It allows autonomous systems to complete complex tasks by dynamically accessing and acting upon external resources.


## Slide 26

_(no text content ? likely image/diagram only)_


## Slide 27

### Tool calling flow

**The code tells LLM what tools they can call**

**The LLM responds with suggested tool name and arguments**

**The code calls function for that tool**

**The code sends prior messages and return value from tool function to LLM**

**The LLM responds based off full history**



## Slide 28

_(no text content ? likely image/diagram only)_


## Slide 29

_(no text content ? likely image/diagram only)_


## Slide 30

_(no text content ? likely image/diagram only)_


## Slide 31

_(no text content ? likely image/diagram only)_


## Slide 32

### Lab: Calculator_Agent

- https://colab.research.google.com/drive/1M1hnCDmaJk8oTIpecQDgd07b9KVQZ34u


## Slide 33

### Evaluator-planner Design Pattern

- In agentic AI systems, Evaluator–Planner and Evaluator–Optimizer loops are design patterns that control how an AI agent improves its outputs over time.
**Evaluator–Planner Loop**

- This pattern is about improving actions or plans.
- How it works:
- The agent creates a plan (sequence of steps to solve a task).
- An evaluator critiques the plan (Is it logical? Missing steps? Inefficient?).
- The planner revises the plan based on feedback.
- Loop continues until the plan is good enough.
- Then the plan is executed.


## Slide 34

### Evaluator-planner Design Pattern



## Slide 35

### Evaluator-planner Design Pattern

- Example:
- Task: “Organize a workshop”
- Planner: “Book venue → Invite speakers → Send emails”
- Evaluator: “You forgot budgeting and scheduling”
**Planner updates plan**

**Repeat until solid plan**

- Where it’s used:
**Multi-step reasoning**

**Task decomposition**

**Autonomous agents (like AutoGPT-style systems)**



## Slide 36

### Evaluator- Optimizer Design Pattern

**Evaluator–Optimizer Loop**

- This pattern is about improving outputs rather than plans.
- How it works:
- The agent generates an output (text, code, answer, etc.).
- An evaluator scores/critiques the output.
- An optimizer modifies the output to improve quality.
- Loop repeats until output meets criteria.


## Slide 37

### Evaluator- Optimizer Design Pattern

- Example:
- Task: “Write an essay”
**Draft 1 generated**

- Evaluator: “Weak introduction, unclear argument”
**Optimizer rewrites**

**Repeat until polished**

- Where it’s used:
**Text refinement (LLM self-improvement)**

**Code generation + debugging**

**RLHF-like setups (feedback loops)**



## Slide 38

### Lab Demo: langchain_evaluator-optimizer-agent

- https://colab.research.google.com/drive/1XrY4CxMomcZeMNsmdmt75g-px_CpO97b#scrollTo=eGCTWR1qTZXd


## Slide 39

### Safety layers & guardrails

- Guardrails for AI agent loops are structured, layered mechanisms—often middleware—that intercept inputs, outputs, and tool calls to ensure AI agents operate within safe, ethical, and authorized boundaries.
- Because agents execute multi-step tasks, these guardrails must extend beyond simple input/output filtering to action-level checks to prevent issues like infinite tool loops and unauthorized actions.


## Slide 40

### Human-in-the-Loop means:

- An AI agent can act autonomously — but humans remain part of critical decision paths.
- HITL is not about slowing agents down. It’s about controlling when autonomy is allowed.
- Guardrails are hard boundaries an agent cannot cross.
- Without guardrails, an agent is not production-ready.


## Slide 41

### Key Safety Layers & Guardrails

- Input Validation (The Firewall): Sanitizes user inputs before they reach the model to prevent prompt injection and jailbreaks.
- Context/Retrieval Guardrails (RAG): Evaluates the retrieved information for accuracy and relevance to prevent hallucinations.
- Output Validation (The Truth Layer): Checks generated text for PII leaks, toxicity, and compliance with ethical standards before reaching the user.
- Agentic Action Guardrails (Runaway Loop Protection): Monitors tool usage, enforcing limits on API calls and requiring human approval for high-risk actions (e.g., deleting data, sending emails).


## Slide 42

### Soft vs. Hard Boundaries:

- Soft (Modular Nodes): Intercept and moderate, providing flexibility for task-specific controls (e.g., in AgentKit).
- Hard (Non-negotiable): Hardcoded limits on agent action space, often managed through formal verification or runtime monitoring.
**Continuous Improvement & Evaluation**

- Guardrails must be treated as a living system, often maintained through continuous monitoring for drift and adversarial attacks. Red teaming is used to identify weaknesses and refine guardrails to enhance security over time.


## Slide 43

### Agent architecture



## Slide 44

- The agent can use a tool to help answer a user's question.
**Tool**

**LLM**

**Single agent with tool**

- Agent architecture:
**Response**

**Request**



## Slide 45

### Single agent with tool

**@tool**

**def get_weather(**

- city: Annotated[str, Field(description="City name, spelled out fully")],
- ) -> dict:
**"""Returns weather data, a dict with temperature and description."""**

- return {"temperature": 72, "description": "Sunny"}
**agent = Agent(client=client,**

**instructions="You're an info agent. Answer questions cheerfully.",**

**tools=[get_weather])**

**response = await agent.run("Whats weather today in San Francisco?")**

**print(response.text)**

- Define tools using Python functions, with typed args, return type, and docstring:
**agent-framework**



## Slide 46

- The agent must decide which tool to use and what order to call tools in.
**Tool A**

**LLM**

**Tool B**

**Tool C**

**Single agent with multiple tools**

- Agent architecture:


## Slide 47

### Single agent with tools

**@tool**

- def get_current_date() -> str:
**return datetime.now().strftime("%Y-%m-%d")**

**@tool**

**def get_weather(**

- city: Annotated[str, Field(description="The city to get weather for")]) -> dict:
- ...
**@tool**

**def get_activities(**

- city: Annotated[str, Field(description="The city to get activities for")],
- date: Annotated[str, Field(description="Date, in format YYYY-MM-DD.")]) -> list:
- ...
- agent = Agent(client=client, instructions="You help users plan their weekends.",
**tools=[get_weather, get_activities, get_current_date])**

- Full example: agent_tools.py
**agent-framework**



## Slide 48

- Lab Activity: Designing an agent capable of multi-step planning.
- Goto https://crewai.com/
**Register for sign in**

**Try with the below prompt**

- I want to build a weekly learning assistant. It should ask for a topic to learn about, then research the topic, find the best resources and generate a personalized study plan.


## Slide 49

### Lab / Activities

**Build a Tetris game**

**Wurzburg city information app**

- Portfolio site development - build a portfolio site for me. take inputs from https://sites.google.com/view/manikandakumar
- Research Paper: To develop improved predictive model for soil stability and landslide susceptibility for multi-source data using explainable AI techniques.
