import argparse

from neat_ai.ai_training_logger import AITrainingLogger


def main():
    parser = argparse.ArgumentParser(
        description="Clear NEAT training rows and AI-generated training decks."
    )
    parser.add_argument(
        "--training-id",
        type=int,
        default=None,
        help="Clear one training run. Omit to clear all training data.",
    )
    parser.add_argument(
        "--keep-legacy-decks",
        action="store_true",
        help="Do not delete old AI deck rows from utils/decks.db.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete data. Without this flag, only a dry run is printed.",
    )
    args = parser.parse_args()

    logger = AITrainingLogger()
    counts = logger.clear_training_data(
        training_id=args.training_id,
        delete_legacy_decks=not args.keep_legacy_decks,
        dry_run=not args.yes,
    )

    action = "Deleted" if args.yes else "Dry run"
    print(f"{action}:")
    for table_name, row_count in counts.items():
        print(f"  {table_name}: {row_count}")

    if not args.yes:
        print("\nRun again with --yes to delete these rows.")


if __name__ == "__main__":
    main()
