---
name: code-checker
description: Security and quality review for code files and technical implementations
metadata:
  author: DevilAgent
  version: 1.0.0
---

# Code Checker Skill

## When to Use
- User submits code snippets or files
- Content contains programming logic
- Need security audit or quality review

## Workflow

1. **Security Scan**
   - Injection vulnerabilities (SQL, XSS, Command)
   - Authentication/Authorization flaws
   - Sensitive data exposure
   - Insecure dependencies

2. **Logic Review**
   - Race conditions
   - Null/undefined handling
   - Boundary conditions
   - Error handling gaps

3. **Quality Check**
   - Code complexity
   - DRY violations
   - Performance bottlenecks
   - Memory leaks

## Output Format
🔴 **MUST FIX** - Security vulnerabilities, crashes, data loss risks
🟡 **SHOULD FIX** - Bugs, poor error handling, maintainability issues
📝 **SUGGESTIONS** - Style, performance, best practices

## Example
User submits Python code with `os.system(user_input)`

Response:
🔴 **MUST FIX**
- Line 15: Command injection vulnerability
  ```python
  os.system(user_input)  # DANGEROUS: arbitrary command execution
  ```
  Fix: Use `subprocess.run()` with explicit args list

🟡 **SHOULD FIX**
- No input validation before processing
- Missing error handling for file operations

Want deeper analysis on any issue? You can specify attack direction.