from rich.console import Console

console = Console(stderr=True, highlight=False, soft_wrap=True)


def log(message: str) -> None:
    console.print(message)


def step(number: int, total: int, message: str) -> None:
    log(f"[cyan]Step {number}/{total}:[/cyan] {message}")


def detail(message: str) -> None:
    log(f"  {message}")
