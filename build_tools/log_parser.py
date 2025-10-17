import re
import pandas as pd
import sys
import os

def parse_log_to_csv(log_file, test_name=None):
    # Regex to detect the start of a new log entry
    log_start_pattern = re.compile(
        r'^\[?(?P<utc_time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)?\]?\s*'
        r'(?P<local_time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})?\s*-\s*'
        r'(?P<level>[A-Z]+)?\s*-\s*(?P<message>.*)'
    )

    parsed = []
    current_entry = None

    with open(log_file, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue

            match = log_start_pattern.match(line)
            if match:
                # Save the previous log entry
                if current_entry:
                    parsed.append(current_entry)

                # Start a new log entry
                data = match.groupdict()
                current_entry = {
                    "UTC_Time": data.get("utc_time"),
                    "Local_Time": data.get("local_time"),
                    "Level": data.get("level"),
                    "Message": data.get("message").strip()
                }
            else:
                # Continuation of previous log message
                if current_entry:
                    current_entry["Message"] += "\n" + line.strip()
                else:
                    # If no current entry, treat as orphan line
                    parsed.append({
                        "UTC_Time": None,
                        "Local_Time": None,
                        "Level": None,
                        "Message": line.strip()
                    })

    # Add the last log entry
    if current_entry:
        parsed.append(current_entry)

    # Convert to DataFrame
    df = pd.DataFrame(parsed)

    # Build CSV file name from log file
    csv_file = os.path.splitext(log_file)[0] + "_parsed.csv"

    # Save parsed logs
    df.to_csv(csv_file, index=False)

    print(f"✅ Parsed logs saved to: {csv_file}")
    print(df.head())

    return csv_file

def extract_test_name(log_file):
    """Extract test name from first line containing --execute"""
    with open(log_file, "r") as f:
        for line in f:
            match = re.search(r"--execute\s+(\w+)", line)
            if match:
                return match.group(1)
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_logs.py <log_file>")
        sys.exit(1)

    log_file = sys.argv[1]
    test_name = extract_test_name(log_file)
    if test_name:
        print(f"Detected test name: {test_name}")
    else:
        print("No test name detected. Parsing entire log.")

    parse_log_to_csv(log_file, test_name)

