"""A drafted option as markdown, for saving to Notion or Medium."""

from agents.content_copy.formats import Format
from agents.content_copy.schemas import Piece, Variant


def page_title(variant: Variant, piece: Piece) -> str:
    if variant.title:
        return variant.title
    topic = " ".join(piece.topic.split())
    return f"{piece.label}: {topic}" if topic else piece.label


def as_markdown(variant: Variant, piece: Piece, fmt: Format, *, for_medium: bool = False) -> str:
    """The option's content. For Medium the title leads the story itself (its
    API keeps the title field out of the post body); for Notion the title is
    the page name, so the body starts with what follows it."""
    blocks: list[str] = []
    if fmt.shape == "article":
        if for_medium:
            blocks.append(f"# {variant.title or page_title(variant, piece)}")
            if variant.subtitle:
                blocks.append(f"*{variant.subtitle}*")
        elif variant.subtitle:
            blocks.append(f"**{piece.subtitle_label or 'Summary'}:** {variant.subtitle}")
        blocks.append(variant.text)
        if variant.tags and not for_medium:
            blocks.append("**Tags:** " + ", ".join(variant.tags))
    elif fmt.shape == "thread":
        total = len(variant.parts)
        blocks.extend(f"**{n}/{total}**\n\n{part}" for n, part in enumerate(variant.parts, 1))
    elif fmt.shape == "email":
        if variant.title:
            blocks.append(f"**Subject:** {variant.title}")
        if variant.subtitle:
            blocks.append(f"**Preview:** {variant.subtitle}")
        blocks.append(variant.text)
    elif fmt.shape == "ad":
        if variant.headlines:
            blocks.append("## Headlines\n" + "\n".join(f"- {h}" for h in variant.headlines))
        if variant.descriptions:
            blocks.append("## Descriptions\n" + "\n".join(f"- {d}" for d in variant.descriptions))
        if variant.text:
            blocks.append("## Primary text\n" + variant.text)
    else:
        blocks.append(variant.text)
    return "\n\n".join(b.strip() for b in blocks if b and b.strip()) + "\n"
