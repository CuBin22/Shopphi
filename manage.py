#!/usr/bin/env python
"""Tiện ích dòng lệnh của Django cho dự án Shopphi."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Shopphi.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Không import được Django. Hãy kích hoạt môi trường ảo và chạy: pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
