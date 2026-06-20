"""
Run all questions from materials/questions.txt and print results.

Usage:
    python run_questions.py            # uses real LLM (requires GROQ_API_KEY in .env)
    python run_questions.py --stub     # uses deterministic stub formatter, no key needed
"""
import sys
import os

from dotenv import load_dotenv
load_dotenv()

from src.loader import load_customers, load_knowledge
from src.bot import SupportBot
from src.formatter import StubFormatter, GroqFormatter


def main():
    use_stub = "--stub" in sys.argv or not os.environ.get("GROQ_API_KEY")

    customers = load_customers("materials/customers.json")
    knowledge = load_knowledge("materials/knowledge.md")

    if use_stub:
        formatter = StubFormatter()
        print("Running with stub formatter (no LLM)\n")
    else:
        formatter = GroqFormatter()
        print("Running with LLM formatter (Groq)\n")

    bot = SupportBot(customers=customers, knowledge_sections=knowledge, formatter=formatter)

    with open("materials/questions.txt", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("|", 1)
        if len(parts) != 2:
            continue

        customer_id = parts[0].strip()
        question = parts[1].strip()

        response = bot.answer(customer_id, question)

        print("=" * 60)
        print(f"Customer : {customer_id}")
        print(f"Question : {question}")
        print(f"Action   : {response.action}")
        print(f"Reply    : {response.text}")
        print()


if __name__ == "__main__":
    main()
