"""Evaluate retrieval quality against QA pairs.

Runs semantic search and structured query tests against a curated set of
question/expected-source pairs, then reports recall@k and MRR.
"""

import json
from pathlib import Path

from ..retrieval.semantic import semantic_search
from ..retrieval.structured import answer_structured

QA_FILE = Path(__file__).resolve().parents[3] / "tests" / "evaluation" / "qa_pairs.json"
TOP_K = 5


def load_qa_pairs() -> list[dict]:
    with open(QA_FILE) as f:
        return json.load(f)


def evaluate_semantic(qa_pairs: list[dict]) -> dict:
    total = len(qa_pairs)
    type_hits = 0
    file_hits = 0
    type_rr_sum = 0.0
    file_rr_sum = 0.0

    print("=" * 72)
    print("  SEMANTIC RETRIEVAL EVALUATION")
    print("=" * 72)

    for q in qa_pairs:
        if q.get("structured"):
            total -= 1
            continue

        query = q["question"]
        gold_type = q["expected_document_type"]
        gold_file = q["expected_filename"]

        results = semantic_search(query, top_k=TOP_K)

        print(f"\nQ: {query}")
        print(f"  Expected type={gold_type}  file={gold_file}")

        type_found = False
        file_found = False

        for rank, r in enumerate(results, start=1):
            marker = "✅" if r["document_type"] == gold_type else " "
            src_type = r["document_type"]
            src_file = r["file"]
            score = r["score"]
            snippet = r["text"][:100].replace("\n", " ")

            print(f"  {marker} Rank {rank}: [{src_type}] {src_file} (score={score:.3f})")
            print(f"             {snippet}...")

            if not type_found and r["document_type"] == gold_type:
                type_hits += 1
                type_rr_sum += 1.0 / rank
                type_found = True

            if not file_found and r["file"] == gold_file:
                file_hits += 1
                file_rr_sum += 1.0 / rank
                file_found = True

        if not type_found:
            print("  ❌ Expected document_type NOT found in top-5")

    recall_type = type_hits / total if total else 0
    recall_file = file_hits / total if total else 0
    mrr_type = type_rr_sum / total if total else 0
    mrr_file = file_rr_sum / total if total else 0

    return {
        "total_questions": total,
        "recall_document_type": recall_type,
        "recall_filename": recall_file,
        "mrr_document_type": mrr_type,
        "mrr_filename": mrr_file,
        "hits_type": type_hits,
        "hits_file": file_hits,
    }


def evaluate_structured(qa_pairs: list[dict]) -> dict:
    total = 0
    correct = 0

    print("\n" + "=" * 72)
    print("  STRUCTURED RETRIEVAL EVALUATION")
    print("=" * 72)

    for q in qa_pairs:
        if not q.get("structured"):
            continue
        total += 1
        query = q["question"]
        pattern = q["expected_answer_pattern"]

        result = answer_structured(query)
        answer = result["answer"]

        found = pattern.lower() in answer.lower()
        marker = "✅" if found else "❌"
        print(f"\n{marker} Q: {query}")
        print(f"  Expected pattern: '{pattern}'")
        print(f"  Answer preview: {answer[:200]}")

        if found:
            correct += 1

    return {
        "total_questions": total,
        "accuracy": correct / total if total else 0,
        "correct": correct,
    }


def main():
    qa_pairs = load_qa_pairs()
    print(f"Loaded {len(qa_pairs)} QA pairs from {QA_FILE}")

    semantic_qs = [q for q in qa_pairs if not q.get("structured")]
    structured_qs = [q for q in qa_pairs if q.get("structured")]

    print(f"  Semantic: {len(semantic_qs)} questions")
    print(f"  Structured: {len(structured_qs)} questions")

    sem_metrics = evaluate_semantic(qa_pairs)
    str_metrics = evaluate_structured(qa_pairs)

    print("\n\n" + "=" * 72)
    print("  RESULTS SUMMARY")
    print("=" * 72)

    print("\nSemantic Retrieval:")
    print(f"  Questions: {sem_metrics['total_questions']}")
    print(f"  Recall@{TOP_K} (document_type): {sem_metrics['recall_document_type']:.2f}  ({sem_metrics['hits_type']}/{sem_metrics['total_questions']})")
    print(f"  MRR (document_type):       {sem_metrics['mrr_document_type']:.3f}")
    print(f"  Recall@{TOP_K} (filename):       {sem_metrics['recall_filename']:.2f}  ({sem_metrics['hits_file']}/{sem_metrics['total_questions']})")
    print(f"  MRR (filename):             {sem_metrics['mrr_filename']:.3f}")

    print("\nStructured Retrieval:")
    print(f"  Questions: {str_metrics['total_questions']}")
    print(f"  Accuracy:  {str_metrics['accuracy']:.2f}  ({str_metrics['correct']}/{str_metrics['total_questions']})")


if __name__ == "__main__":
    main()
