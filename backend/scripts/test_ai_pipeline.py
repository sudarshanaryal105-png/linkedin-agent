"""Standalone sanity check for the AI generation pipeline — no DB, no Supabase, no LinkedIn
needed. Just verifies your ANTHROPIC_API_KEY and the prompt produce a sensible draft.

Usage:
    python scripts/test_ai_pipeline.py "I completed this certification, announce it" cert.jpg [more images...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai_pipeline import ImageInput, generate_draft  # noqa: E402

MIME_BY_SUFFIX = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)

    prompt_text = sys.argv[1]
    image_paths = [Path(p) for p in sys.argv[2:]]

    images = []
    for path in image_paths:
        mime_type = MIME_BY_SUFFIX.get(path.suffix.lower())
        if not mime_type:
            raise SystemExit(f"Unsupported file type: {path}")
        images.append(ImageInput(bytes_=path.read_bytes(), mime_type=mime_type))

    result = generate_draft(prompt_text, optional_context=None, images=images)

    print("\n=== POST TEXT ===\n")
    print(result.post_text)
    print("\n=== HASHTAGS ===\n")
    print(", ".join(f"#{tag}" for tag in result.hashtags))
    print("\n=== SELECTED IMAGES (by input index) ===\n")
    print(result.selected_image_indexes)
    print("\n=== REASONING ===\n")
    print(result.reasoning)
    print(f"\n(tokens: {result.input_tokens} in / {result.output_tokens} out, ~${result.cost_usd:.4f})")


if __name__ == "__main__":
    main()
