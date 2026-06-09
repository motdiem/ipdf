# The Pocket Reader

A short sample document that exercises the styling **ipdf** preserves when it
builds an iPhone-friendly PDF.

## Why a phone-shaped page?

When you read a PDF on a phone you almost always *fit it to the screen width*.
What matters then is the **ratio** between the font size and the page width —
not the absolute paper size. ipdf uses a small, phone-shaped page so the text
lands at a comfortable size with a short, readable line length.

### Things it keeps intact

- **Bold** and *italic* and even ***both at once***
- `inline code` and longer code blocks
- Nested lists
    - like this
    - and this
- [Links](https://example.com) to elsewhere

Ordered lists work too:

1. First
2. Second
3. Third

> Blockquotes are styled with a left rule so quoted passages stay distinct
> from the surrounding prose, which helps a lot on a narrow column.

#### A small table

| Setting    | Default      | Why                          |
| ---------- | ------------ | ---------------------------- |
| Page       | 3.5" × 7.58" | iPhone aspect ratio          |
| Font       | sans-serif   | crisp at small sizes         |
| Font size  | 11 pt        | large after fit-to-width     |
| Line height| 1.5          | airy, easy to track          |

##### A code block

```python
def greet(name: str) -> str:
    """Long lines wrap instead of being clipped off the narrow page."""
    return f"Hello, {name}! Welcome to a comfortably readable PDF on your phone."
```

---

That's it — open the generated PDF on your phone and it should *just read well*.
