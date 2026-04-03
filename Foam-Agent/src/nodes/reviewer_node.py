# reviewer_node.py
from pydantic import BaseModel, Field
from typing import List
from services.review import review_error_logs, generate_rewrite_plan, detect_openfoam10_infeasible


def reviewer_node(state):
    """
    Reviewer node: Reviews the error logs and provides analysis and suggestions
    for fixing the errors. This node only focuses on analysis, not file modification.
    """
    print(f"============================== Reviewer Analysis ==============================")
    if len(state["error_logs"]) == 0:
        print("No error to review.")
        return state
    
    # Stateless review via service
    history_text = state.get("history_text") or []
    review_content, updated_history = review_error_logs(
        tutorial_reference=state.get('tutorial_reference', ''),
        foamfiles=state.get('foamfiles'),
        error_logs=state.get('error_logs'),
        user_requirement=state.get('user_requirement', ''),
        similar_case_advice=state.get('similar_case_advice'),
        history_text=history_text,
    )

    print(review_content)

    feasibility = detect_openfoam10_infeasible(
        user_requirement=state.get('user_requirement', ''),
        error_logs=state.get('error_logs', []),
        review_analysis=review_content,
    )

    if feasibility.get("unsupported_openfoam10"):
        reason = feasibility.get("reason", "requirement beyond OpenFOAM10 capabilities")
        print(f"Terminating reviewer loop: {reason}")
        return {
            "history_text": updated_history,
            "review_analysis": review_content,
            "termination_reason": "unsupported_openfoam10_requirement",
            "termination_detail": reason,
            "loop_count": state.get("loop_count", 0) + 1,
        }

    rewrite_plan = generate_rewrite_plan(
        foamfiles=state.get('foamfiles'),
        error_logs=state.get('error_logs', []),
        review_analysis=review_content,
        user_requirement=state.get('user_requirement', ''),
    )
    print(f"Rewrite plan: {rewrite_plan}")

    return {
        "history_text": updated_history,
        "review_analysis": review_content,
        "rewrite_plan": rewrite_plan,
        "loop_count": state.get("loop_count", 0) + 1,
        "input_writer_mode": "rewrite",
    }

