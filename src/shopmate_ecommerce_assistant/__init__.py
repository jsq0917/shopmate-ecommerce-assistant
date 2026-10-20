"""ShopMate application package."""

__version__ = "0.1.0"


def main() -> None:
    """Run the development API server through the configured CLI entry point."""
    from shopmate_ecommerce_assistant.main import run

    run()
