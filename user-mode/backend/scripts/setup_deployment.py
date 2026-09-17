"""Create local container secrets once; never print or overwrite them."""

from pathlib import Path
from secrets import token_urlsafe


def main() -> None:
    target = Path(__file__).resolve().parents[2] / "deploy" / ".env"
    content = "\n".join([
        f"POSTGRES_PASSWORD={token_urlsafe(32)}",
        f"GUIDE_CREDENTIAL_ROOT={token_urlsafe(32)}",
        f"GUIDE_MEDIA_ENCRYPTION_KEY={token_urlsafe(32)}",
        "GUIDE_SUPABASE_URL=", "VITE_SUPABASE_PUBLISHABLE_KEY=", "",
    ])
    try:
        with target.open("x", encoding="utf-8") as output:
            output.write(content)
    except FileExistsError:
        print("The deployment configuration already exists; nothing was changed.")
        return
    print("Created user-mode/deploy/.env. Keep it private and back it up with the data.")


if __name__ == "__main__":
    main()
