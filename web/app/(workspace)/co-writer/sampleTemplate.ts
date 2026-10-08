const FENCE = "```";

export const CO_WRITER_SAMPLE_TEMPLATE = `# EnjoyLearning Co-Writer

> EnjoyLearning's built-in writing canvas for notes, reports, tutorials, and AI-assisted drafts.

### Features

- Support Standard Markdown / CommonMark / GFM for everyday writing
- Real-time preview for headings, tables, code, math, flowchart, and sequence diagrams
- AI editing workflows for rewrite, shorten, and expand
- HTML tag decoding for tags like <sub>, <sup>, <abbr>, and <mark>
- A practical starter draft for product docs and learning content

## Headers (Underline)

EnjoyLearning Learning Note
=============

EnjoyLearning Study Outline
-------------

### Characters

----

~~Deprecated behavior~~ <s>Legacy formatting path</s>
*Italic* _Italic_
**Emphasis** __Emphasis__
***Emphasis Italic*** ___Emphasis Italic___

Superscript: X<sup>2</sup>, Subscript: O<sub>2</sub>

**Abbreviation(link HTML abbr tag)**

The <abbr title="Large Language Model">LLM</abbr> layer powers EnjoyLearning while the <abbr title="Retrieval Augmented Generation">RAG</abbr> layer provides grounded knowledge support.

### Blockquotes

> EnjoyLearning helps students turn questions into structured understanding.
>
> "Learn deeply, write clearly.", [EnjoyLearning](#enjoylearning-co-writer)

### Links

[EnjoyLearning Co-Writer](#enjoylearning-co-writer "co-writer section")

[EnjoyLearning Learning Note](#enjoylearning-learning-note)

[CommonMark specification](https://commonmark.org)

[Reference link][sample-doc-anchor]

[sample-doc-anchor]: #enjoylearning-learning-note

### Code Blocks

#### Inline code

\`pip install -r requirements.txt\`

#### Code Blocks (Indented style)

    import json
    config = json.loads('{"capability": "chat"}')
    print("EnjoyLearning is ready.", config["capability"])

#### Python

${FENCE}python
import asyncio


async def run_demo() -> str:
    steps = ["read the question", "gather context", "draft the answer"]
    for step in steps:
        print(f"- {step}")
    return steps[-1]


print(asyncio.run(run_demo()))
${FENCE}

#### JSON config

${FENCE}json
{
  "app_name": "EnjoyLearning",
  "default_capability": "chat",
  "enabled_tools": ["rag", "web_search", "exec", "reason"],
  "ui": {
    "co_writer_template": true
  }
}
${FENCE}

#### HTML code

${FENCE}html
<section class="learning-card">
  <h1>EnjoyLearning</h1>
  <p>Write, revise, and organize learning content with AI.</p>
</section>
${FENCE}

### Images

![](/logo.png)

> EnjoyLearning brand mark used inside the co-writer template.

### Lists

- EnjoyLearning Chat
- EnjoyLearning Co-Writer
- EnjoyLearning Research

1. Draft a concept note
2. Ask AI to refine it
3. Export the polished markdown

### Tables

Feature       | Description
------------- | -------------
Co-Writer     | Draft and refine Markdown content
Chat          | Ask questions and iterate ideas
Research      | Build structured multi-step reports

| Capability    | Primary Use Case                     |
| ------------- | ------------------------------------ |
| \`chat\`       | General tutoring and guidance        |
| \`deep_solve\` | Structured problem solving           |
| \`deep_question\` | Question generation and validation |

### Markdown extras

- [x] Draft a product note
- [x] Add references and structure
- [ ] Polish the final explanation
  - [ ] Check headings
  - [ ] Check citations

### TeX (LaTeX)

$$ E=mc^2 $$

Inline $$E=mc^2$$ appears in physics notes, and Inline $$a^2+b^2=c^2$$ appears in geometry notes.

$$\\sqrt{3x-1}+(1+x)^2$$

$$ \\sin(\\alpha)^{\\theta}=\\sum_{i=0}^{n}(x^i + \\cos(f))$$

### FlowChart

${FENCE}flow
st=>start: Student asks a question
op=>operation: EnjoyLearning analyzes intent
cond=>condition: Need deep workflow?
chat=>operation: Answer with chat capability
solve=>operation: Route to deep solve
e=>end: Return structured response

st->op->cond
cond(no)->chat
cond(yes)->solve
chat->e
solve->e
${FENCE}

### Sequence Diagram

${FENCE}seq
Student->EnjoyLearning: Ask for help
EnjoyLearning->KnowledgeBase: Load context
Note right of EnjoyLearning: Collect memory\\nand relevant knowledge
EnjoyLearning-->Student: Return guided response
Student->>EnjoyLearning: Request rewrite in co-writer
${FENCE}

### End
`;
