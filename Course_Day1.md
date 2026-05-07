# Foundations of Agentic AI ? Day 1

Source: `FOUNDATIONS OF AGENTIC AI Day 1.pptx` ? 38 slides

---

## Slide 1

### Day 1 FOUNDATIONS OF AGENTIC AI

- Agentic AI - Autonomous AI vs Traditional AI - Agent lifecycle and capabilities - Types of autonomy in AI systems - Rule-based agents vs LLM-driven agents - Real-world examples of agents - maturity levels of autonomous systems - Application domains aligned to sustainability & green digital transition.
- Interactive brainstorming: Where can agents be used in business?
- List of Experiments:
- Lab 1: Setup of Python environment, LangChain/Flowise/AutoGen tools
- Lab 2: Creating a simple LLM-based task planner
- Lab 3: Agent behavior exploration through prompts & tasks.


## Slide 2

### What is agentic AI?

- Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows – allowing enterprises to make decisions and get work done more effectively.
- AI agents can make decisions, plan, and adapt to achieve predefined goals - with little human intervention or completely autonomously.


## Slide 3

### An AI agent uses an LLM to run

- tools in a loop to achieve a goal.
- Agents are often augmented by:
**Context**

**Memory**

**Planning**

**Humans**

**Agentic AI**



## Slide 4

### Autonomous AI vs Traditional AI

**Agentic AI**

- Operates autonomously, making decisions and pursuing goals, asking for human guidance when needed.
- Analyzes situations and finds the best path for moving forward.
- Designs, executes, and optimizes workflows to achieve specific objectives.
- Adapts to changes and continuously self-improves.
**Traditional AI**

- Provides valuable insights based on data.
- Is a key ingredient in more sophistic Agentic AI systems.
- Automates or assists with specific, simple tasks.
- Often requires manual retraining to adapt to changes in its environment.


## Slide 5

_(no text content ? likely image/diagram only)_


## Slide 6

_(no text content ? likely image/diagram only)_


## Slide 7

### Lab Activity: Build a simple snake game



## Slide 8

### Discussion on “what is AI-ML-DL, LLM”

**Discussion on “AI Agents Vs. Agentic AI”**



## Slide 9

### Agent lifecycle and capabilities

- Agentic Development Lifecycle (ADLC) is for designing, deploying, governing, and continuously evolving intelligent agents at enterprise scale.
- It enables an environment where execution is autonomous, workflows are dynamic, and decisions are made in real time.


## Slide 10

### Managing agent behavior across dynamic environments

**Tracing and auditing decisions made in real time**

**Maintaining continuous oversight of always-on AI systems**

**Enforcing safety controls and policy compliance at runtime**

**Coordinating multiple agents working together across workflows**

**Ensuring reliability as AI operations scale across the enterprise**

**Agent lifecycle and capabilities**



## Slide 11

### ADLC Framework



## Slide 12

### Step 1: Goal Definition – Set the intent before you build

- Step 2: Build Product Requirements Document (PRD) – Translate vision into actionable direction.
- Step 3: Write Skills – Equip agents with the right capabilities.
- Step 4: Orchestrate Agents – Coordinate actions across systems seamlessly.
- Step 5: Monitoring and Feedback – Observe performance and learn continuously.
- Steps 6: Continuous Execution and Deployment – Improve constantly while systems run.
**ADLC Framework - Steps**



## Slide 13

_(no text content ? likely image/diagram only)_


## Slide 14

_(no text content ? likely image/diagram only)_


## Slide 15

### Activity: Prompting with LLMs Vs Agents (with ChatGPT and KIMI)

- Make me an app to help me learn machine learning from scratch. It should provide learning resources, timelines, and have a way for me to track my progress


## Slide 16

### ChatGPT



## Slide 17

### KIMI



## Slide 18

### Rule-based agents vs LLM-driven agents



## Slide 19

### Rule-based agents

- Rule-based AI agents follow explicitly defined instructions, executing specific actions when given a predetermined input. These systems operate deterministically, ensuring that the same input always leads to the same output.
- Rule-based AI agents are systems that function based on a set of explicit rules manually programmed by developers. These rules follow an “if-then” logic structure, meaning the system performs a specific action when a given condition is met. Since these rules are pre-programmed, the agent cannot adapt beyond what has been explicitly defined by developers.


## Slide 20

### Characteristics of Rule-Based AI Systems

- Predefined Logic: Rule-based systems operate strictly within manually programmed rules and logic structures.
- Deterministic Nature: Given the same input, a rule-based agent will always return the same output, ensuring consistent behavior.
- Structured Decision-Making: These systems rely on predefined workflows, ensuring reliable operation within known scenarios.


## Slide 21

### Challenges of Rule-Based AI

- Limited Adaptability: Rule-based AI agents struggle when dealing with scenarios not explicitly covered by their predefined rules. If an unforeseen input occurs, the system may fail to respond effectively.
- Scalability Challenges: As complexity increases, the number of rules grows exponentially, making rule-based systems difficult to manage and maintain.
- Inability to Handle Ambiguity: These systems do not possess contextual understanding, making them ineffective for tasks requiring natural language comprehension or reasoning beyond fixed logic.


## Slide 22

### Practical Applications of Rule-Based AI in Business

- Simple Chatbots: Many early customer support bots operate using rule-based logic to provide predefined responses to frequently asked questions.
- Automated Data Entry and Validation: Rule-based AI is used in data validation systems that check entries against a fixed set of rules.
- Compliance Checking: In industries such as finance and healthcare, rule-based AI agents ensure that processes adhere to regulations by following strict rules.


## Slide 23

- Large Language Model (LLM)-based AI agents leverage deep learning techniques to process and generate human-like text.
- These systems are trained on massive datasets, allowing them to understand language, infer context, and generate coherent responses.
- Unlike rule-based agents, LLM-based AI does not rely on predefined rules but instead adapts dynamically based on learned patterns and contextual information.
**LLM-driven agents**



## Slide 24

### Characteristics & Benefits of LLM-Based Agents

- Contextual Awareness: LLM-based AI agents can interpret and respond to queries based on context rather than fixed rules.
- Self-Learning Capability: These agents can be fine-tuned with additional data to improve performance in specific domains.
- Scalable and Adaptive: They can handle a broad range of tasks, from answering open-ended questions to generating long-form content.
- High Flexibility: Unlike rule-based agents, LLM-based AI agents can manage diverse inputs and respond dynamically to various scenarios, making them suitable for complex applications such as conversational AI and content generation.
- Natural Language Understanding: These models can comprehend, process, and generate human-like text, allowing for more sophisticated interactions.
- Improved User Experience: Provides engaging and personalized interactions compared to rule-based systems, enhancing customer service & virtual assistants.


## Slide 25

### Challenges & Constraints of LLM-Based Agents

- Computational Requirements: Training and running LLM-based AI agents require significant computational resources, making them costlier than rule-based systems.
- Lack of Transparency: The decision-making process of LLMs is often seen as a “black box,” making it difficult to interpret how specific outputs are generated.
- Potential for Hallucination: Since LLMs generate responses probabilistically, they sometimes produce inaccurate or misleading outputs.


## Slide 26

### Cases Across Industries

- Conversational AI and Virtual Assistants: LLMs power AI-driven chatbots and virtual assistants capable of understanding context and responding dynamically.
- Automated Content Generation: LLMs generate articles, summaries, and creative content, streamlining content production.
- AI-Powered Customer Support: Many modern customer service applications use LLMs to provide more natural, context-aware responses to customer inquiries.


## Slide 27

_(no text content ? likely image/diagram only)_


## Slide 28

### Real-world examples of agents



## Slide 29

### Demo

**Please type out an essay on topic “AI in Healthcare” using antigravity**



## Slide 30

### Real-world examples of agents



## Slide 31

_(no text content ? likely image/diagram only)_


## Slide 32

_(no text content ? likely image/diagram only)_


## Slide 33

### Maturity levels of autonomous systems

- Autonomous systems maturity is generally categorized into six levels (0-5), ranging from fully manual operations to fully self-governing systems.
**Key stages include, for example in manufacturing,**

**No automation (L0/L1),**

**Basic automation (L1/L2),**

**Context-aware adaptation (L3),**

**Semi-autonomous (L4), and**

- Fully autonomous operations.


## Slide 34

- Level 0 - Manual/No Autonomy: All tasks and decisions are performed by humans.
- Level 1 - Assisted Operations/Automation: Automated systems assist with specific tasks, but humans make all decisions.
- Level 2 - Partial Automation/Connected: Systems are connected and provide some context-aware functionality, but require human supervision.
- Level 3 - Conditional/Adaptable Automation: Systems are self-adaptable, predicting and reacting to events, while providing recommendations to human operators.
- Level 4 - High/Semi-Autonomous: Systems operate independently within specific boundaries and contexts, with infrequent human intervention.
- Level 5 - Full Automation/Autonomy: The system is fully self-learning and self-optimizing under all conditions, requiring no human intervention.
**Common Autonomous Systems Maturity Levels**



## Slide 35

### Application domains

- Autonomous Driving: The SAE J3016 standard defines similar levels (0-5) from no automation to full self-driving, commonly cited in vehicle development.
- Manufacturing: Research from and focuses on the transition from traditional manufacturing to smart, self-optimizing factories (e.g., using a 5-stage Enterprise AI Maturity Model).
- Telecommunications: Often focuses on reaching Level 4, defined as AI-led networks that operate autonomously.


## Slide 36

### Interactive brainstorming

**Where can agents be used in business?**



## Slide 37

### Lab Activity: Building E-mail support agent

- Go to https://zapier.com/
**Get Connected with your Gmail**

**Create  New Agent**

**Fill the Instructions to follow**

**Add necessary tools**

**Publish**

**Test by sending mails**



## Slide 38

### List of Experiments

- Lab 1: Setup of Python environment, LangChain / Flowise / AutoGen tools.
- Lab 2: Creating a simple LLM-based task planner.
- Lab 3: Agent behaviour exploration through prompts & tasks.
