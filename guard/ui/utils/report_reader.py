#!/usr/bin/env python3
"""
Report Reader - Robust reader for Stack Doctor reports
Handles MD/JSON formats with atomic reads and proper error handling
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

# Setup logger
logger = logging.getLogger(__name__)


def get_latest_report_path() -> Optional[Path]:
    """
    Get the latest Stack Doctor report path.

    Prefers MD if present and non-empty.
    Fallback to JSON if present and non-empty.
    Returns None if neither valid.
    """
    try:
        # Canonical report directory
        repo_root = Path(__file__).parent.parent.parent.parent
        canonical_dir = repo_root / "shared_data" / "reports" / "stack_doctor"

        # Check for latest.md first (preferred)
        md_path = canonical_dir / "latest.md"
        if md_path.exists():
            # Check if non-empty (not just whitespace)
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        logger.info(f"report_reader: using latest.md")
                        return md_path
                    else:
                        logger.info(f"report_reader: skipping empty file (size=0 or whitespace-only): {md_path}")
            except Exception as e:
                logger.warning(f"report_reader: failed to read {md_path}: {e}")

        # Fallback to latest.json
        json_path = canonical_dir / "latest.json"
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        logger.info(f"report_reader: using latest.json")
                        return json_path
                    else:
                        logger.info(f"report_reader: skipping empty file (size=0): {json_path}")
            except Exception as e:
                logger.warning(f"report_reader: failed to read {json_path}: {e}")

        # No valid report found
        return None

    except Exception as e:
        logger.error(f"report_reader: error finding report path: {e}")
        return None


def read_report_text(path: Path) -> str:
    """
    Read report text from path.

    If .md → return text as is.
    If .json → pretty-render a short markdown summary + fenced JSON block.

    Safety:
    - Treat size==0 or whitespace-only as empty.
    - On JSON parse error, display error banner + raw excerpt.
    - All reads UTF-8 (no BOM).
    """
    try:
        if not path.exists():
            return ""

        # Check file age - if updated < 1s ago, wait briefly for atomic write to complete
        file_age = time.time() - path.stat().st_mtime
        if file_age < 1.0:
            logger.info(f"report_reader: file updated {file_age:.2f}s ago, waiting 200ms for atomic write")
            time.sleep(0.2)

        # Read file content (UTF-8, no BOM)
        with open(path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig strips BOM if present
            content = f.read()

        # Check if empty or whitespace-only
        if not content.strip():
            logger.info(f"report_reader: file is empty or whitespace-only: {path}")
            return ""

        # Handle based on file extension
        if path.suffix.lower() == '.md':
            # Markdown - return as is
            return content

        elif path.suffix.lower() == '.json':
            # JSON - pretty-render as markdown
            try:
                data = json.loads(content)

                # Extract key fields
                timestamp = data.get("timestamp", "unknown")
                overall_status = data.get("overall_status", "UNKNOWN")
                summary = data.get("summary", [])
                checks = data.get("checks", {})

                # Build markdown summary
                md_lines = [
                    f"# Stack Doctor Report (JSON)",
                    f"",
                    f"**Overall Status**: {overall_status}",
                    f"**Timestamp**: {timestamp}",
                    f"",
                    f"## Summary",
                    ""
                ]

                for item in summary:
                    md_lines.append(f"- {item}")

                md_lines.extend([
                    "",
                    "## Checks",
                    ""
                ])

                for check_name, check_result in checks.items():
                    status = check_result.get("status", "UNKNOWN")
                    message = check_result.get("message", "")
                    status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
                    md_lines.append(f"- {status_emoji} **{check_name}**: {message}")

                md_lines.extend([
                    "",
                    "## Raw JSON",
                    "",
                    "```json",
                    json.dumps(data, indent=2, ensure_ascii=False),
                    "```"
                ])

                return "\n".join(md_lines)

            except json.JSONDecodeError as e:
                # JSON parse error - show error banner + raw excerpt
                logger.warning(f"report_reader: JSON parse error in {path}: {e}")

                # Get first 500 chars as excerpt
                excerpt = content[:500] if len(content) > 500 else content

                error_md = f"""# ⚠️ Report Parse Error

**Error**: Failed to parse JSON report

**Details**: {str(e)}

**File**: {path.name}

## Raw Content (excerpt)

```
{excerpt}
```

**Suggestion**: The report file may be corrupted. Try running Stack Doctor again.
"""
                return error_md

        else:
            # Unknown format - return as plain text
            return f"# Report Content\n\n```\n{content}\n```"

    except Exception as e:
        logger.error(f"report_reader: error reading {path}: {e}")
        return f"# ⚠️ Error Reading Report\n\n**Error**: {str(e)}\n\n**File**: {path}"


def get_report_content() -> Tuple[bool, str]:
    """
    Get the latest report content.

    Returns:
        (success: bool, content: str)
        - success=True, content=markdown text if report found
        - success=False, content=empty state message if no report
    """
    try:
        report_path = get_latest_report_path()

        if report_path is None:
            # No report found - return empty state
            repo_root = Path(__file__).parent.parent.parent.parent
            canonical_dir = repo_root / "shared_data" / "reports" / "stack_doctor"

            empty_state = f"""# 📋 No Report Found

**Status**: No Stack Doctor report is available yet.

**What to do**:
1. Click **Run Stack Doctor** to generate a new report
2. Wait a few seconds for the diagnosis to complete
3. Click **View Report** again to see the results

**Expected report locations**:
- `{canonical_dir / 'latest.md'}` (preferred)
- `{canonical_dir / 'latest.json'}` (fallback)

**Note**: If you just ran Stack Doctor, the file may still be writing. Please wait a moment and try again.
"""
            return (False, empty_state)

        # Read report content
        content = read_report_text(report_path)

        if not content:
            # File exists but is empty
            empty_state = f"""# ⚠️ Empty Report

**Status**: Report file exists but is empty.

**File**: `{report_path}`

**What to do**:
1. Run Stack Doctor again to generate a fresh report
2. Check if the file is being written (it may be in progress)

**Suggestion**: If this persists, there may be a write permission issue.
"""
            return (False, empty_state)

        return (True, content)

    except Exception as e:
        logger.error(f"report_reader: error getting report content: {e}")
        error_msg = f"""# ⚠️ Error Loading Report

**Error**: {str(e)}

**What to do**:
1. Check file permissions in `shared_data/reports/stack_doctor/`
2. Try running Stack Doctor again
3. Check the logs for more details
"""
        return (False, error_msg)


if __name__ == "__main__":
    # Test the reader
    print("🔍 Report Reader - Test")
    print("=" * 50)

    # Test get_latest_report_path
    report_path = get_latest_report_path()
    if report_path:
        print(f"✅ Found report: {report_path}")

        # Test read_report_text
        content = read_report_text(report_path)
        print(f"✅ Read {len(content)} characters")
        print("\nFirst 200 chars:")
        print(content[:200])
    else:
        print("❌ No report found")

    # Test get_report_content
    success, content = get_report_content()
    print(f"\n{'✅' if success else '❌'} get_report_content: success={success}")
    print(f"Content length: {len(content)}")
