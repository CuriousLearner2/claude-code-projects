#!/bin/bash
# Path to your project directory
PROJECT_DIR="/Users/gautambiswas/Gemini Code/coding-assistants-projects/bangla"
cd "$PROJECT_DIR"

# Run the dynamic python script
/opt/homebrew/bin/python3 "$PROJECT_DIR/daily_bangla_news.py" >> "$PROJECT_DIR/daily_email_log.log" 2>&1
