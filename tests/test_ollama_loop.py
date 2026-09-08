import asyncio

from llm.ollama_agent import run_interactive


def test_interactive_loop_answers_until_exit(capsys) -> None:
    prompts = iter(["first question", "second question", "exit"])
    answered: list[str] = []

    def fake_input(_: str) -> str:
        return next(prompts)

    async def fake_ask(prompt: str) -> str:
        answered.append(prompt)
        return f"answer for {prompt}"

    asyncio.run(run_interactive(fake_ask, fake_input))

    output = capsys.readouterr().out
    assert answered == ["first question", "second question"]
    assert "answer for first question" in output
    assert "answer for second question" in output
    assert "Goodbye." in output