import os
from typing import Any, Dict, List, Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_functions_agent, AgentExecutor

from server import tools as dbtools


def build_agent(system_prompt: str):
    model = ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", "gemini-1.5-flash"),
        temperature=0.2,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

    @tool
    def find_books(q: str, by: Literal["title", "author"], session_id: str) -> Dict[str, Any]:
        """Search for books by title or author."""
        return dbtools.find_books(session_id=session_id, q=q, by=by)

    @tool
    def create_order(customer_id: int, items: List[Dict[str, Any]], session_id: str) -> Dict[str, Any]:
        """Create an order for a customer and reduce stock."""
        return dbtools.create_order(session_id=session_id, customer_id=customer_id, items=items)

    @tool
    def restock_book(isbn: str, qty: int, session_id: str) -> Dict[str, Any]:
        """Increase stock for a book."""
        return dbtools.restock_book(session_id=session_id, isbn=isbn, qty=qty)

    @tool
    def update_price(isbn: str, price: float, session_id: str) -> Dict[str, Any]:
        """Update the price of a book."""
        return dbtools.update_price(session_id=session_id, isbn=isbn, price=price)

    @tool
    def order_status(order_id: int, session_id: str) -> Dict[str, Any]:
        """Get order status and items."""
        return dbtools.order_status(session_id=session_id, order_id=order_id)

    @tool
    def inventory_summary(session_id: str) -> Dict[str, Any]:
        """Get inventory totals and low-stock titles."""
        return dbtools.inventory_summary(session_id=session_id)

    tools = [
        find_books,
        create_order,
        restock_book,
        update_price,
        order_status,
        inventory_summary,
    ]

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_openai_functions_agent(
        llm=model,
        tools=tools,
        prompt=prompt,
    )

    return AgentExecutor(agent=agent, tools=tools, verbose=False)
