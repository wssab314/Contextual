# Contextual

> ## What is Contextual?
>
> **Contextual** is an AI-powered bot that acts as your development team's automated knowledge manager. It lives where your team collaborates—in DingTalk, Slack, or Microsoft Teams—and silently works in the background to eliminate the gap between your codebase and your project management system.
>
> ## The Problem We Solve
>
> In fast-paced development cycles, the crucial link between a piece of code and the business requirement it fulfills is often lost. This "context gap" leads to:
>
> * **Slow Onboarding:** New engineers struggle to understand the history and purpose of the codebase.
> * **Painful Maintenance:** Debugging and refactoring become a detective work of digging through old tickets and asking colleagues.
> * **Ineffective Code Reviews:** Reviewers lack the full story behind a change, making it hard to assess its business logic.
>
> ## How It Works
>
> **Contextual** reverses this trend by creating a seamless, automated workflow:
>
> 1.  **Analyze:** It monitors your Git repository for every new commit.
> 2.  **Understand:** Using a specialized Language Model, it analyzes the semantic intent of the code `diff` and the `commit message`.
> 3.  **Recommend:** It searches your Jira instance and identifies the single most relevant task with high confidence.
> 4.  **Interact:** It sends a simple, non-intrusive prompt to the developer in their chat client: *"I believe this commit is related to JIRA-123. Is that correct?"*
> 5.  **Link:** With a single click on `[✅ Yes, link it]`, a permanent, queryable link is created. Over time, **Contextual** learns from your team's feedback, becoming progressively smarter and more accurate.
>
> By building this living network of knowledge, **Contextual** empowers your team to build better software, faster.