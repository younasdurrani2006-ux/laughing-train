# Job Application Automation Bot

This repository provides a configurable automation bot that can fill in and submit job application forms automatically. It is built on top of [Playwright](https://playwright.dev/) and exposes a declarative YAML configuration language so that each job posting can be automated without writing Python code.

> ⚠️ **Important:** Many job boards prohibit automated submissions in their Terms of Service. Use this project responsibly and only against workflows you are allowed to automate.

## Features

- Headless or headed browser automation through Playwright.
- Declarative steps (`goto`, `fill`, `click`, `upload`, `check`, `select`, `wait`, `assert_text`, `press`, `hover`) that map directly onto browser actions.
- Jinja2 templating for reusing profile data (name, email, links, etc.) across multiple applications.
- Dry-run mode to review the actions that would be executed without touching the browser.
- Structured logging that helps you understand what the bot is doing at each step.

## Quick start

1. **Install dependencies**

   ```bash
   pip install .
   playwright install
   ```

2. **Copy the example configuration**

   ```bash
   cp examples/sample_config.yaml my_jobs.yaml
   ```

3. **Update the profile information and job steps** in `my_jobs.yaml` so that they match the forms you want to automate.

4. **Run the bot**

   ```bash
   job-bot run my_jobs.yaml
   ```

   You can pass `--headless/--no-headless` to control the browser UI and `--dry-run` to only print the steps without launching a browser.

## Configuration format

The configuration file is composed of three sections:

- `profile`: reusable details about you (name, contact info, links, resumes, etc.).
- `browser`: global browser settings such as headless mode and base timeout.
- `jobs`: an array of job-specific automation flows.

Each job contains a `url` and a list of `steps`. Every step has an `action` and optional parameters depending on the action type. String values are rendered with Jinja2 so you can reference `profile` fields like `{{ profile.full_name }}` or `{{ profile.resume }}`.

The template context also exposes a helper `path(<relative_path>)` that resolves files relative to the configuration file. This is useful for pointing to documents such as resumes or cover letters kept alongside the YAML file.

See [`examples/sample_config.yaml`](examples/sample_config.yaml) for a fully annotated example.

## Extending the bot

New actions can be added by extending `job_bot.bot.ACTION_HANDLERS`. Each handler receives the Playwright `page`, the rendered step definition, and the runtime context. You can implement logic for complex multi-page flows, captcha solving integrations, or API-based submissions.

## Disclaimer

Automating job applications may violate site policies and could lead to account suspension. This project is provided for educational purposes only. The maintainers are not responsible for any misuse.
