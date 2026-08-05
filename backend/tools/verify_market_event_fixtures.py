from generate_market_event_fixtures import FIXTURE_DIR, verify_tree


def main() -> int:
    files = verify_tree(FIXTURE_DIR)
    print(f"verified {len(files)} deterministic fixture artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
