import gift_parser
import pprint

sample_gift = """
// MCQ Question
What is the capital of France? {=Paris ~London ~Berlin ~Madrid}

// Numerical Question
What is 2 + 2? {#4}

// Another MCQ
Which of these is a fruit? {~Carrot =Apple ~Potato ~Broccoli}
"""

print("--- Parsing GIFT ---")
questions = gift_parser.parse_gift(sample_gift)
pprint.pprint(questions)

print("\n--- Shuffling Exam ---")
shuffled = gift_parser.shuffle_exam(questions)
pprint.pprint(shuffled)

# Verify correct mapping is preserved
for i, q in enumerate(shuffled):
    print(f"\nQ{i+1}: {q['text']}")
    if q['type'] == 'MCQ':
        print(f"  Options: {q['options']}")
        print(f"  Answer Key: {q['ans']} (Index {q['ans_idx']})")
        print(f"  Correct content: {q['options'][q['ans_idx']]}")
    else:
        print(f"  Answer: {q['ans']}")
