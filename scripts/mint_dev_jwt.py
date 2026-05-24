#!/usr/bin/env python3
"""Mint a dev JWT using AUTH_JWT_SECRET / AUTH_JWT_ALGORITHM from .env."""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt  # pylint: disable=wrong-import-position

from app.config.settings import get_settings  # pylint: disable=wrong-import-position


def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a dev JWT for API testing.")
    parser.add_argument(
        "--sub",
        required=True,
        help="User id for the sub claim (e.g. user-123)",
    )
    parser.add_argument(
        "--expires-in-hours",
        type=int,
        default=24,
        help="Token lifetime in hours (default: 24)",
    )
    args = parser.parse_args()

    auth = get_settings().auth
    payload = {
        "sub": args.sub,
        "exp": datetime.now(timezone.utc) + timedelta(hours=args.expires_in_hours),
    }
    token = jwt.encode(
        payload,
        auth.jwt_secret.get_secret_value(),
        algorithm=auth.jwt_algorithm,
    )
    print(token)


if __name__ == "__main__":
    main()
