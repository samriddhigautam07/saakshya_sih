<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Validation rules live in src/lib/validation/engine.ts as pure functions and mock issuer checks in src/lib/verification/mock-issuer.ts; keep them UI-free so rules can change without touching pages.
- App data (applications, review decisions, audit history, checklist config) persists in browser localStorage via src/lib/store.ts; swap this module to move to a database.
