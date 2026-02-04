import re
import random

def parse_gift(text):
    """
    Very basic GIFT parser for MCQ and Numerical questions.
    Supports:
    - MCQ: {=Correct ~Wrong ~Wrong}
    - Numerical: {#Value} or {#Value:Tolerance}
    """
    # Remove comments and empty lines
    clean_lines = []
    for line in text.splitlines():
        if line.strip().startswith('//'):
            continue
        clean_lines.append(line)
    
    clean_text = "\n".join(clean_lines)
    
    # Split by double newline to get individual questions
    blocks = re.split(r'\n\s*\n', clean_text.strip())
    questions = []
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        # Extract question text and answer part
        # Format: Question text { answer }
        match = re.search(r'(.*)\{(.*)\}', block, re.DOTALL)
        if match:
            q_text = match.group(1).strip()
            a_part = match.group(2).strip()
            
            # Numeric
            if a_part.startswith('#'):
                val_str = a_part[1:].strip()
                # Handle tolerance if present (e.g. #10:0.5)
                if ':' in val_str:
                    target, tolerance = val_str.split(':')
                    ans = float(target)
                else:
                    ans = float(val_str)
                
                questions.append({
                    "text": q_text,
                    "type": "Numeric",
                    "ans": ans
                })
            # MCQ
            else:
                # Options are prefixed with = (correct) or ~ (wrong)
                options = []
                correct_idx = -1
                
                # Split by space or newline before ~ or =
                # A more robust way is to find all parts starting with ~ or =
                parts = re.split(r'([=~])', a_part)
                # parts looks like ['', '=', 'Correct', '~', 'Wrong']
                
                current_prefix = None
                for i in range(1, len(parts), 2):
                    prefix = parts[i]
                    content = parts[i+1].strip()
                    if prefix == '=':
                        correct_idx = len(options)
                    options.append(content)
                
                if options:
                    questions.append({
                        "text": q_text,
                        "type": "MCQ",
                        "options": options,
                        "ans_idx": correct_idx # This is the index in the UNSHUFFLED list
                    })
        else:
            # Maybe it's a simple description or unsupported format
            pass
            
    return questions

def shuffle_exam(questions):
    """
    Shuffles questions and their options.
    Returns a list of shuffled questions with updated correct answer indices/values.
    """
    shuffled_qs = questions.copy()
    random.shuffle(shuffled_qs)
    
    final_exam = []
    for i, q in enumerate(shuffled_qs):
        new_q = q.copy()
        if q["type"] == "MCQ":
            options = q["options"].copy()
            correct_content = options[q["ans_idx"]]
            
            random.shuffle(options)
            new_ans_idx = options.index(correct_content)
            
            new_q["options"] = options
            new_q["ans_idx"] = new_ans_idx
            # Add a human-readable answer for the key
            new_q["ans"] = chr(65 + new_ans_idx) # 'A', 'B', etc.
            
        final_exam.append(new_q)
        
    return final_exam
