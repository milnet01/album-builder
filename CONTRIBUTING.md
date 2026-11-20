# Contributing to Album Builder

Thank you for helping.

## Checking a translation

Album Builder comes in Afrikaans, Arabic, Hebrew, Spanish, French,
German and Portuguese as well as English. An AI drafted these
translations, and no native speaker has checked them yet. If you speak
one of these languages, your eye is the most useful help there is.

### Report a wording fix

1. Open the app and pick your language under **View > Language**. Close
   and reopen the app.
2. Use the app as normal. Note any text that is wrong, awkward or
   too formal.
3. Open a new issue at
   [github.com/milnet01/album-builder/issues](https://github.com/milnet01/album-builder/issues).
   A free GitHub account is needed.
4. In the issue, give:
   - the language;
   - where you saw the text (which tab, menu or window);
   - what the app shows now;
   - what it should say.

   A screenshot helps. Several fixes can go in one issue.

### Fix it yourself

Each language is one file in `src/album_builder/translations/`, named by
its language code: `af`, `ar`, `he`, `es`, `fr`, `de`, `pt`. Each line
pairs the English text, on the left, with its translation, on the right:

```json
"Add to playlist": "Voeg by snitlys",
```

Change only the right-hand side. Keep anything in curly brackets, such
as `{composer}`, exactly as it is. The app fills those in. Then open a
pull request.

## Reporting a bug or asking for a feature

Open an issue at
[github.com/milnet01/album-builder/issues](https://github.com/milnet01/album-builder/issues).
Say what you did, what you expected and what happened instead.

## Code changes

The "For developers" section of [`README.md`](README.md) shows how to
run the app and its tests. `./local-CI.sh` runs the same checks as
GitHub's CI. Please run it before opening a pull request.
