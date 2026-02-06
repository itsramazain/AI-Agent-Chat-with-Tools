# Library Desk Agent (AI Agent + Tools + SQLite)

<img width="1863" height="855" alt="image" src="https://github.com/user-attachments/assets/d9f93d21-1aa4-4fa7-a14a-cbd9fdf5f9c2" />


This project is a local “Library Desk Agent” chat application that answers library questions and performs inventory/order actions by calling **backend tools** that **read/write a SQLite database**. The core idea is that the assistant never “guesses” database facts—whenever the user asks about books, stock, orders, or prices, the agent uses tools that query/modify the DB and then summarizes the results back to the user.

---

## High-Level Architecture

The app is a full-stack system with three main layers:

1. **Frontend (React UI)**

- Displays sessions (left sidebar) and chat messages (center).
- Sends user messages to the backend.
- Loads previous sessions and chat history.

2. **Backend (FastAPI)**

- Exposes REST endpoints for sessions, chat, and debugging tool logs.
- Stores user/assistant messages in the database.
- Runs an agent (LangChain) which decides which tools to call.
- Returns the assistant reply to the frontend.

3. **Database (SQLite)**

- Stores domain entities (books, customers, orders, order_items).
- Stores chat history (messages) by session.
- Stores tool execution logs (tool_calls) for traceability.

### The Core Principle

**LLM = reasoning + tool selection**  
**Tools = source of truth + DB mutations**  
This separation ensures correctness: stock/order status always comes from the DB, not from the model’s imagination.

---

## Repository Structure

Typical layout:

- `app/`
  - React frontend (chat UI)
- `server/`
  - FastAPI server (endpoints + agent + tools)
- `db/`
  - SQL schema and seed data
- `prompts/`
  - System prompt that guides the agent’s behavior
- `docs/`
  - Optional documentation assets (e.g., the screenshot referenced above)

---

## Database Design

### Domain tables

#### `books`

Represents the library’s inventory.

- `isbn` (PK): stored as a string identifier
- `title`, `author`
- `stock`: current inventory level
- `price`: current selling price
- timestamps: `created_at`, `updated_at`

The `stock` column is central because it is mutated by:

- `create_order` (decrement stock)
- `restock_book` (increment stock)

#### `customers`

Represents people who can place orders.

- `id` (PK)
- `name`, `email`

#### `orders`

Order header / summary.

- `id` (PK)
- `customer_id` (FK → customers.id)
- `status` (e.g., `created`, `fulfilled`)
- `created_at`

#### `order_items`

Line items for each order.

- `order_id` (FK → orders.id)
- `isbn` (FK → books.isbn)
- `qty`
- `unit_price`

`unit_price` is stored at purchase time so that later price updates do not change historical order totals.

### Chat + Observability tables

#### `messages`

Stores all chat messages per session.

- `session_id`: conversation identifier
- `role`: `user` or `assistant`
- `content`
- `created_at`

This enables:

- loading past sessions
- reconstructing the conversation context for the agent

#### `tool_calls`

Stores every tool invocation with input and output.

- `session_id`
- `name` (tool name)
- `args_json` (serialized tool arguments)
- `result_json` (serialized tool output)
- `created_at`

This table is extremely useful for debugging agent behavior: you can see exactly what the model requested and what the DB returned.

### Foreign keys and integrity

SQLite foreign key enforcement is enabled to avoid inconsistent data (e.g., order items referencing missing orders). Where cascading behavior is used (like removing order_items when an order is deleted), it prevents “orphan rows”.

---

## Backend (FastAPI) Overview

The backend is the “control center”. It handles:

- session creation and listing
- storing and fetching messages
- running the agent
- exposing tool logs

### Key Endpoints

#### `POST /api/sessions`

Creates a new session ID (typically a UUID). The UI uses this as a new chat thread.

#### `GET /api/sessions`

Lists sessions, usually ordered by recent activity. This powers the sidebar session list.

#### `GET /api/sessions/{session_id}/messages`

Loads chat history for a session. The UI renders these messages in the chat window.

#### `GET /api/sessions/{session_id}/tool-calls` (debug/optional)

Loads tool call logs for a session. This is helpful for verifying that the agent is actually using tools correctly.

#### `POST /api/chat`

This is the most important route: it implements the chat loop.

Typical flow inside `/api/chat`:

1. Validate request (must include `session_id` and a non-empty message)
2. Insert the user message into `messages`
3. Load recent chat history from `messages` to provide context to the agent
4. Invoke the agent with:
   - the new user message
   - the previous chat messages
   - available tools
5. The agent may call tools; each tool reads/writes the DB and logs into `tool_calls`
6. The agent returns a final text response
7. Insert the assistant response into `messages`
8. Return `{ reply: "..." }` to the UI

This ensures:

- every conversation turn is persisted
- tool actions are reproducible and auditable

---

## Transactions and DB Safety

Database writes (especially orders and stock updates) must be atomic.

A transaction wrapper is used so that:

- if anything fails mid-operation, changes are rolled back
- partial updates do not corrupt the DB

This matters most in `create_order`, which performs multiple writes:

- create order
- create order_items
- decrement stock

If there’s an error (like insufficient stock), the operation should not leave the DB in a half-updated state.

---

## Tools Layer (DB Functions)

Tools are backend functions that represent “safe, structured actions” the agent can call.
They are the only place where the DB is mutated.

Each tool follows a consistent pattern:

1. Validate inputs
2. Query or update DB
3. Build a JSON result
4. Log the tool call (`tool_calls`)
5. Return the JSON result to the agent

### Tools implemented

#### `find_books({ q, by })`

Searches `books` by partial match.

- `by = "title"` searches by title
- `by = "author"` searches by author
  Returns a list of matching books with relevant fields (isbn, title, author, stock, price).

#### `create_order({ customer_id, items })`

Creates an order and reduces stock.

- Validates customer exists
- Validates each ISBN exists
- Validates stock is sufficient for each item
- Inserts into `orders`
- Inserts into `order_items`
- Updates `books.stock = books.stock - qty`
  Returns:
- `order_id`
- purchased items
- updated stock for affected books

This tool is the main “action” used in the sample scenario:
“We sold 3 copies of Clean Code to customer 2 today…”

#### `restock_book({ isbn, qty })`

Increments inventory for a book.

- Looks up the book
- Adds qty to `stock`
  Returns the new stock.

#### `update_price({ isbn, price })`

Updates a book’s price.
Returns the new price.

#### `order_status({ order_id })`

Returns order header + its line items.
Useful for:
“What’s the status of order 3?”

#### `inventory_summary()`

Returns an overview such as:

- total titles
- total stock
- a low-stock list (titles under a threshold)

This is designed for operational quick checks.

---

## Agent Layer (LangChain)

The agent is responsible for:

- understanding user intent in natural language
- deciding which tool(s) to call
- calling tools with correct arguments
- combining results into a helpful final answer

### Prompting strategy

A system prompt defines guardrails like:

- prefer tools for DB facts
- do not hallucinate stock/order status
- be concise and include key values (order id, stock)

### Tool orchestration examples

**Example A: create order**
User: “We sold 3 copies of Clean Code to customer 2 today. Create the order and adjust stock.”

- Agent calls `create_order(customer_id=2, items=[{isbn: ..., qty: 3}])`
- Tool decrements stock
- Agent replies with order id and updated stock

**Example B: multi-step**
User: “Restock The Pragmatic Programmer by 10 and list all books by Andrew Hunt.”

- Agent calls `restock_book(...)`
- Agent calls `find_books(by="author", q="Andrew Hunt")`
- Agent replies with new stock + list of matches

---

## Frontend (React UI)

The UI is intentionally simple and mirrors typical support-desk chat tools.

### Layout

- **Left sidebar**
  - Session list (each session_id)
  - New session button
  - Optional “Show tools” debugging view

- **Main chat**
  - Message list (user and assistant)
  - Text input + Send button

### Frontend data flow

1. On load, UI calls `GET /api/sessions` to show existing sessions.
2. When a session is selected, UI calls `GET /api/sessions/{id}/messages`.
3. When the user sends a message:
   - UI calls `POST /api/chat`
   - UI renders assistant reply from the response
4. Optional debug:
   - UI calls `GET /api/sessions/{id}/tool-calls`
   - renders JSON tool logs for transparency

### Why a debug tool view helps

It demonstrates the core assignment requirement: the assistant must actually use tools to read/write the DB. Tool logs give immediate proof.

---

## Practical Implementation Notes

### ISBN formatting

Real-world ISBNs may appear with hyphens (e.g., `978-0132350884`) while the DB stores them without hyphens (`9780132350884`). A robust implementation often normalizes ISBN input (remove hyphens/spaces) inside tool functions before querying.

### Determinism and reliability

For tool-driven agents, the model temperature is kept low. This makes:

- tool calling more consistent
- responses more stable for repeated tests
- behavior more “agent-like” and less “creative”

### Why store both `messages` and `tool_calls`

- `messages` = conversational record
- `tool_calls` = operational trace
  Together, they let you reconstruct what happened and why.

---

## What to Look At First (Code Tour)

If you’re reviewing the code:

1. `db/schema.sql`

- Understand tables and relationships.

2. `server/tools.py`

- Core business logic + DB mutations.
- Tool-call logging is implemented here.

3. `server/agent.py`

- The bridge between user language and tool calls.

4. `server/main.py`

- The chat loop endpoint (`/api/chat`) and session/message endpoints.

5. `app/src/App.tsx`

- UI layout and how it calls the backend.

6. `app/src/api.ts`

- Centralized backend API calls.

---

## Screenshot

The screenshot at the top demonstrates:

- multiple sessions listed on the left
- successful tool-driven actions like:
  - creating an order and updating stock
  - restocking and searching by author
  - checking order status

To display it in this README, store the image at:

`docs/ui.png`

and keep the Markdown image reference:

`![Library Desk Agent UI](docs/ui.png)`

to Run:

1.

cd app; npm install; npm run dev

2.

copy .env.example .env

# edit .env and set OPENAI_API_KEY=your_key

uvicorn server.main:app --reload --port 8000
